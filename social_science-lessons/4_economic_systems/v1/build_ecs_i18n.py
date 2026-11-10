"""
build_ecs_i18n.py

Builds audio_index_*.js files for:
  Economic Systems and How Choices are Made — Class 9 Economics Chapter 8

Run from anywhere:
    python build_ecs_i18n.py
    python build_ecs_i18n.py --only en
    python build_ecs_i18n.py --only en,hi,ja,as
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path

# ── .env loader ───────────────────────────────────────────────────────────────
def _load_env():
    here = Path(__file__).resolve().parent
    # Walk every ancestor, not a fixed depth: some lessons sit deeper than
    # others (duplicated chapter folders), which put .env out of reach.
    for candidate in [p / ".env" for p in [here, *here.parents]]:
        if candidate.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(candidate)
                return
            except ImportError:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
                return

_load_env()

TTS_KEY       = os.environ.get("GOOGLE_TTS_API_KEY",        "").strip()
TRANSLATE_KEY = os.environ.get("GOOGLE_TRANSLATION_API_KEY","").strip() or TTS_KEY
AZURE_KEY     = os.environ.get("AZURE_TTS_API_KEY",         "").strip()

TTS_URL       = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={TTS_KEY}"
TRANSLATE_URL = f"https://translation.googleapis.com/language/translate/v2?key={TRANSLATE_KEY}"

OUT_DIR = Path(__file__).resolve().parent

LESSON_DATA_FILE = "lesson_data_ecs.js"

# ── voice configs ─────────────────────────────────────────────────────────────
LOCALE_TTS = {
    "en": [{"languageCode": "en-IN", "name": "en-IN-Chirp3-HD-Aoede"}],
    "hi": [
        {"languageCode": "hi-IN", "name": "hi-IN-Wavenet-A",  "ssmlGender": "FEMALE"},
        {"languageCode": "hi-IN", "name": "hi-IN-Standard-A", "ssmlGender": "FEMALE"},
    ],
    "ja": [
        {"languageCode": "ja-JP", "name": "ja-JP-Neural2-B",  "ssmlGender": "FEMALE"},
        {"languageCode": "ja-JP", "name": "ja-JP-Wavenet-B",  "ssmlGender": "FEMALE"},
        {"languageCode": "ja-JP", "name": "ja-JP-Standard-A", "ssmlGender": "FEMALE"},
    ],
    "as": [
        {"languageCode": "as-IN", "name": "as-IN-YashicaNeural", "ssmlGender": "FEMALE"},
    ],
}

TRANSLATE_CODES = {"hi": "hi", "ja": "ja", "as": "as"}

SKIP_KEYS = frozenset({
    "icon", "bgClass", "type", "correct", "id",
    "canvasBg", "image", "audio", "url", "video",
    "defaultLocale", "supportedLocales",
})

# ── translation ───────────────────────────────────────────────────────────────
_trans_cache: dict[tuple[str, str], str] = {}

def translate_text(text: str, target: str) -> str:
    if not text.strip():
        return text
    key = (text, target)
    if key in _trans_cache:
        return _trans_cache[key]
    payload = json.dumps({"q": text, "source": "en", "target": target, "format": "text"},
                         ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        TRANSLATE_URL, data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())["data"]["translations"][0]["translatedText"]
            _trans_cache[key] = result
            return result
    except Exception as e:
        print(f"  [translate error → {target}] {e}", flush=True)
        return text

def translate_node(node, target: str):
    if isinstance(node, dict):
        return {k: (v if k in SKIP_KEYS else translate_node(v, target)) for k, v in node.items()}
    if isinstance(node, list):
        return [translate_node(i, target) for i in node]
    if isinstance(node, str) and node.strip():
        return translate_text(node, target)
    return node

# ── string collection ─────────────────────────────────────────────────────────
def collect_strings(node) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k not in SKIP_KEYS:
                found |= collect_strings(v)
    elif isinstance(node, list):
        for item in node:
            found |= collect_strings(item)
    elif isinstance(node, str) and node.strip():
        found.add(node)
    return found

# ── TTS ───────────────────────────────────────────────────────────────────────
def audio_fname(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16] + ".mp3"

def _audio_config(voice: dict) -> dict:
    """MP3 config. Chirp3-HD voices reject `pitch`, so omit it for those."""
    cfg = {"audioEncoding": "MP3", "speakingRate": 0.92, "volumeGainDb": 4.0}
    if "Chirp3-HD" not in voice.get("name", ""):
        cfg["pitch"] = -1.0
    return cfg

def tts_google(text: str, voice: dict) -> tuple[str, str]:
    payload = json.dumps({
        "input": {"text": text},
        "voice": {k: voice[k] for k in ("languageCode", "name", "ssmlGender") if k in voice},
        "audioConfig": _audio_config(voice),
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        TTS_URL, data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read()).get("audioContent", ""), ""
    except urllib.error.HTTPError as e:
        return "", f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
    except Exception as e:
        return "", str(e)

def tts_azure(text: str, voice: dict) -> tuple[str, str]:
    region = "eastus"
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    clean = html.escape(text.replace("%", " percent ").replace("&", " and "))
    ssml = (f"<speak version='1.0' xml:lang='{voice['languageCode']}'>"
            f"<voice name='{voice.get('name', 'as-IN-YashicaNeural')}'>{clean}</voice></speak>")
    for attempt in range(8):
        try:
            time.sleep(0.35)
            req = urllib.request.Request(url, data=ssml.encode("utf-8"), headers={
                "Ocp-Apim-Subscription-Key": AZURE_KEY,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                "User-Agent": "AIEducationPlatform",
            })
            with urllib.request.urlopen(req, timeout=120) as r:
                return base64.b64encode(r.read()).decode("utf-8"), ""
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2.0 * (attempt + 1)
                print(f"      [Azure 429] retry in {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            return "", f"Azure HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
        except Exception as e:
            wait = min(4.0 * (attempt + 1), 30.0)
            print(f"      [Azure timeout/err attempt {attempt+1}] {str(e)[:80]} — retry in {wait:.0f}s", flush=True)
            time.sleep(wait)
    return "", "Azure TTS failed after retries"

def synth(text: str, loc: str) -> str:
    voices = LOCALE_TTS.get(loc, [])
    print(f"  [{loc}] {text[:60].replace(chr(10),' ')!r}…", flush=True)
    for i, voice in enumerate(voices):
        b64, err = tts_azure(text, voice) if loc == "as" else tts_google(text, voice)
        if b64:
            if i > 0:
                print(f"        ✓ fallback: {voice.get('name')}", flush=True)
            return b64
        print(f"        ✗ {voice.get('name', loc)}: {err[:120]}", flush=True)
    print(f"  [FAIL] all voices failed for [{loc}]", flush=True)
    return ""

# ── write helpers ─────────────────────────────────────────────────────────────
def write_audio_index(path: Path, mapping: dict) -> None:
    body = ("// Auto-generated — do not edit by hand\n"
            "window.__lessonAudioIndex = "
            + json.dumps(mapping, ensure_ascii=False, indent=2)
            + ';\nwindow.__lessonAudioMime = "audio/mp3";\n')
    path.write_text(body, encoding="utf-8")

def write_lesson_data(path: Path, root: dict) -> None:
    body = ("// Auto-generated — do not edit by hand\n"
            "window.__lessonData = "
            + json.dumps(root, ensure_ascii=False, indent=2)
            + ";\n")
    path.write_text(body, encoding="utf-8")

# ── parse lesson_data_*.js ────────────────────────────────────────────────────
def _js_to_json(js: str) -> str:
    """Best-effort conversion of a JS object literal to JSON."""
    js = re.sub(r'//[^\n]*', '', js)
    js = re.sub(r',\s*([}\]])', r'\1', js)
    out = []; i = 0; n = len(js)
    while i < n:
        c = js[i]
        if c == "'":
            i += 1; s = '"'
            while i < n:
                ch = js[i]
                if ch == '\\':
                    nxt = js[i+1] if i+1 < n else ''
                    if nxt == "'": s += "'"; i += 2
                    elif nxt == '"': s += '\\"'; i += 2
                    else: s += ch + nxt; i += 2
                elif ch == "'": i += 1; break
                elif ch == '"': s += '\\"'; i += 1
                elif ch == '\n': s += '\\n'; i += 1
                else: s += ch; i += 1
            s += '"'; out.append(s); continue
        if c == '`':
            i += 1; s = '"'
            while i < n:
                ch = js[i]
                if ch == '`': i += 1; break
                elif ch == '\\': nxt = js[i+1] if i+1 < n else ''; s += ch + nxt; i += 2
                elif ch == '"': s += '\\"'; i += 1
                elif ch == '\n': s += '\\n'; i += 1
                else: s += ch; i += 1
            s += '"'; out.append(s); continue
        if c == '"':
            s = '"'; i += 1
            while i < n:
                ch = js[i]; s += ch
                if ch == '\\': i += 1; s += js[i] if i < n else ''
                elif ch == '"': i += 1; break
                i += 1
            out.append(s); continue
        m2 = re.match(r'([A-Za-z_$][A-Za-z0-9_$]*)(\s*:)', js[i:])
        if m2:
            out.append('"' + m2.group(1) + '"' + m2.group(2)); i += len(m2.group(0)); continue
        out.append(c); i += 1
    return ''.join(out)

def parse_lesson_data(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.search(r'window\.__lessonData\s*=\s*(\{[\s\S]*\})\s*;?\s*$', text)
    raw = m.group(1) if m else text[text.index("{"):text.rindex("}")+1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    return json.loads(_js_to_json(raw))

# ── audio build ───────────────────────────────────────────────────────────────
def build_audio(locale_pack: dict, loc: str) -> None:
    strings = sorted(collect_strings(locale_pack), key=len)
    print(f"\n[audio:{loc}] {len(strings)} strings to synthesise", flush=True)

    audio_dir = OUT_DIR / "audio" / loc
    audio_dir.mkdir(parents=True, exist_ok=True)

    index: dict[str, str] = {}
    reused = 0

    for text in strings:
        fname = audio_fname(text)
        fpath = audio_dir / fname
        rel   = f"audio/{loc}/{fname}"
        if fpath.exists() and fpath.stat().st_size > 0:
            index[text] = rel
            reused += 1
            continue
        b64 = synth(text, loc)
        if b64:
            fpath.write_bytes(base64.b64decode(b64))
            index[text] = rel
        time.sleep(0.12)

    write_audio_index(OUT_DIR / f"audio_index_{loc}.js", index)
    print(f"  {len(index)} clips ({reused} reused) → audio_index_{loc}.js", flush=True)

# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try: sys.stdout.reconfigure(encoding="utf-8")
        except Exception: pass

    parser = argparse.ArgumentParser(
        description="Build audio for Economic Systems (ecs)")
    parser.add_argument("--only", default=None,
                        help="Comma-separated locales, e.g. en  or  en,hi,ja,as")
    args = parser.parse_args()

    only: set[str] | None = {x.strip() for x in args.only.split(",") if x.strip()} if args.only else None
    all_locales    = ["en", "hi", "ja", "as"]
    target_locales = [l for l in all_locales if not only or l in only]

    if any(l in target_locales for l in ("en", "hi", "ja")) and not TTS_KEY:
        print("ERROR: GOOGLE_TTS_API_KEY not set in .env"); sys.exit(1)
    if "as" in target_locales and not AZURE_KEY:
        print("ERROR: AZURE_TTS_API_KEY not set in .env"); sys.exit(1)
    if any(l in target_locales for l in ("hi", "ja", "as")) and not TRANSLATE_KEY:
        print("ERROR: GOOGLE_TRANSLATION_API_KEY not set in .env"); sys.exit(1)

    data_path = OUT_DIR / LESSON_DATA_FILE
    if not data_path.exists():
        print(f"ERROR: {LESSON_DATA_FILE} not found in {OUT_DIR}"); sys.exit(1)
    print(f"Lesson data: {data_path.name}", flush=True)

    root = parse_lesson_data(data_path)
    existing = root.get("locales", {})
    en_data  = existing.get("en", {})
    if not en_data:
        print("ERROR: no 'en' locale in lesson_data"); sys.exit(1)

    locales: dict = {}
    for loc in all_locales:
        if only and loc not in only:
            locales[loc] = existing.get(loc, {})
            continue
        if loc == "en":
            locales["en"] = deepcopy(en_data)
        else:
            print(f"\nTranslating _ui + _sec → {loc}…", flush=True)
            ex = existing.get(loc, {})
            locales[loc] = {
                "_ui":  translate_node(deepcopy(en_data.get("_ui",  {})), TRANSLATE_CODES[loc]),
                "_sec": translate_node(deepcopy(en_data.get("_sec", [])), TRANSLATE_CODES[loc]),
                "_les": ex.get("_les", []),
            }

    root["locales"]          = locales
    root["defaultLocale"]    = "en"
    root["supportedLocales"] = ["en", "hi", "ja", "as"]
    write_lesson_data(data_path, root)
    print(f"\nWrote {data_path.name}", flush=True)

    for loc in target_locales:
        pack = locales.get(loc)
        if pack:
            build_audio(pack, loc)

    print("\n✓ Done!", flush=True)

if __name__ == "__main__":
    main()
