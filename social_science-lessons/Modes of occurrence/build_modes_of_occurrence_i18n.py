"""
build_modes_of_occurrence_i18n.py

Builds/updates lesson_data.js (adding Assamese locale) and audio_index_*.js files.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path

# Look for .env in script dir AND parent dirs up to project root
def _load_env():
    here = Path(__file__).resolve().parent
    for candidate in [here / ".env", here.parent / ".env", here.parent.parent / ".env", here.parent.parent.parent / ".env"]:
        if candidate.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(candidate)
                return
            except ImportError:
                # Manual parse fallback
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        os.environ.setdefault(k.strip(), v.strip())
                return
_load_env()

# ──────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────
TTS_KEY = os.environ.get("GOOGLE_TTS_API_KEY", "")
TRANSLATE_KEY = os.environ.get("GOOGLE_TRANSLATION_API_KEY", "") or TTS_KEY
TTS_URL = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={TTS_KEY}"
TRANSLATE_URL = f"https://translation.googleapis.com/language/translate/v2?key={TRANSLATE_KEY}"

OUT_DIR = Path(__file__).resolve().parent

LOCALE_TTS = {
    "en": {"languageCode": "en-IN", "name": "en-IN-Wavenet-C", "ssmlGender": "FEMALE"},
    "hi": [
        {"languageCode": "hi-IN", "name": "hi-IN-Wavenet-A", "ssmlGender": "FEMALE"},
        {"languageCode": "hi-IN", "name": "hi-IN-Standard-A", "ssmlGender": "FEMALE"},
    ],
    "ja": [
        {"languageCode": "ja-JP", "name": "ja-JP-Neural2-B", "ssmlGender": "FEMALE"},
        {"languageCode": "ja-JP", "name": "ja-JP-Wavenet-B", "ssmlGender": "FEMALE"},
        {"languageCode": "ja-JP-Standard-A"},
    ],
    "as": [
        {"languageCode": "as-IN", "name": "as-IN-YashicaNeural", "ssmlGender": "FEMALE"},
        {"languageCode": "as-IN", "name": "as-IN-PriyomNeural", "ssmlGender": "MALE"},
    ],
}

LOCALE_TRANSLATE_CODES = {
    "hi": "hi",
    "ja": "ja",
    "as": "as",
}

# Skip translating keys whose values should not be translated
SKIP_KEYS = frozenset({"icon", "bgClass", "type", "correct", "id", "canvasBg", "image", "audio", "url", "video"})

# ──────────────────────────────────────────
# TRANSLATION HELPERS
# ──────────────────────────────────────────

_translation_cache: dict[tuple[str, str], str] = {}

def translate_text(text: str, target_lang: str) -> str:
    """Translate a single string via Google Cloud Translation API v2."""
    if not text.strip():
        return text
    cache_key = (text, target_lang)
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]

    payload = json.dumps({"q": text, "source": "en", "target": target_lang, "format": "text"},
                         ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        TRANSLATE_URL,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
            translated = data["data"]["translations"][0]["translatedText"]
            _translation_cache[cache_key] = translated
            return translated
    except Exception as e:
        print(f"  [TRANSLATE ERROR] {target_lang}: {str(e)[:120]}", flush=True)
        return text  # fall back to English

LESSON_DATA_PATH_FOR_MERGE = Path(__file__).resolve().parent / "lesson_data.js"


def _merge_locale(en_node, prev_en, prev_loc, target_lang: str):
    """Reuse the existing translation wherever the English source is unchanged.

    Re-translating a whole pack from English discards every hand-correction
    already made to a locale (proper nouns, terminology, layout-sensitive short
    forms). This walks the English tree alongside the PREVIOUS English and the
    PREVIOUS translated pack: where an English string has not changed, the
    previous translated string is kept verbatim and no API call is made. Only
    new or changed English is sent to the translator.
    """
    if isinstance(en_node, dict):
        out = {}
        for k, v in en_node.items():
            if k in SKIP_KEYS:
                out[k] = v
                continue
            pe = prev_en.get(k) if isinstance(prev_en, dict) else None
            pl = prev_loc.get(k) if isinstance(prev_loc, dict) else None
            out[k] = _merge_locale(v, pe, pl, target_lang)
        return out
    if isinstance(en_node, list):
        out = []
        for i, item in enumerate(en_node):
            pe = prev_en[i] if isinstance(prev_en, list) and i < len(prev_en) else None
            pl = prev_loc[i] if isinstance(prev_loc, list) and i < len(prev_loc) else None
            out.append(_merge_locale(item, pe, pl, target_lang))
        return out
    if isinstance(en_node, str) and en_node.strip():
        if (isinstance(prev_loc, str) and prev_loc.strip()
                and isinstance(prev_en, str) and prev_en == en_node):
            return prev_loc
        return translate_text(en_node, target_lang)
    return en_node


def _load_prev_locales(data_path):
    """Previous locales dict from an existing lesson_data.js, or {}."""
    try:
        from pathlib import Path as _P
        p = _P(data_path)
        if not p.exists():
            return {}
        txt = p.read_text(encoding="utf-8")
        start = txt.index("{")
        end = txt.rindex("}") + 1
        return json.loads(txt[start:end]).get("locales", {}) or {}
    except Exception as e:
        print(f"  [merge] could not read existing translations: {str(e)[:90]}", flush=True)
        return {}


def _build_locale_preserving(en_source, loc, target_lang, data_path):
    """Translate `loc`, keeping any existing translation whose English is unchanged."""
    prev = _load_prev_locales(data_path)
    prev_loc = prev.get(loc) or {}
    prev_en = prev.get("en") or {}
    if prev_loc and prev_en:
        print(f"\nMerging {loc}: keeping existing strings where English is unchanged...", flush=True)
        return _merge_locale(deepcopy(en_source), prev_en, prev_loc, target_lang)
    print(f"\nTranslating to {target_lang}...", flush=True)
    return translate_node(deepcopy(en_source), target_lang)

def translate_node(node, target_lang: str):
    """Recursively translate all string values in a dict/list, skipping SKIP_KEYS."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in SKIP_KEYS:
                out[k] = v
            else:
                out[k] = translate_node(v, target_lang)
        return out
    elif isinstance(node, list):
        return [translate_node(item, target_lang) for item in node]
    elif isinstance(node, str) and node.strip():
        return translate_text(node, target_lang)
    return node

def build_locale(en_data: dict, target_lang: str) -> dict:
    """Build a translated locale pack from en_data."""
    print(f"\nTranslating to {target_lang}...", flush=True)
    return translate_node(deepcopy(en_data), target_lang)

# ──────────────────────────────────────────
# TTS HELPERS
# ──────────────────────────────────────────

def _voice_payload(voice: dict) -> dict:
    out = {"languageCode": voice["languageCode"]}
    name = voice.get("name", "").strip()
    if name:
        out["name"] = name
    if voice.get("ssmlGender"):
        out["ssmlGender"] = voice["ssmlGender"]
    return out

def tts_one(text: str, voice: dict) -> tuple[str, str]:
    """Returns (base64_mp3_or_empty, error_or_empty)."""
    import time
    import html
    lang_code = voice.get("languageCode", "")
    
    # Clean and escape text for SSML
    clean_text = text
    if lang_code.startswith("as"):
        clean_text = clean_text.replace("%", " শতাংশ")
        clean_text = clean_text.replace("&", " আৰু ")
        clean_text = clean_text.replace("<", "তকৈ কম ")
    clean_text = html.escape(clean_text)

    if lang_code.startswith("as"):
        azure_key = os.environ.get("AZURE_TTS_API_KEY", "").strip()
        if not azure_key:
            return "", "AZURE_TTS_API_KEY not found in environment"
        region = "eastus"
        url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        ssml = f"""<speak version='1.0' xml:lang='{lang_code}'>
            <voice name='{voice.get("name", "as-IN-YashicaNeural")}'>
                {clean_text}
            </voice>
        </speak>"""
        req = urllib.request.Request(
            url,
            data=ssml.encode("utf-8"),
            headers={
                "Ocp-Apim-Subscription-Key": azure_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                "User-Agent": "AIEducationPlatform"
            }
        )
        for attempt in range(4):
            try:
                time.sleep(0.3)
                with urllib.request.urlopen(req, timeout=120) as r:
                    return base64.b64encode(r.read()).decode("utf-8"), ""
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait_sec = 2.0 * (attempt + 1)
                    print(f"      [Azure 429 Throttled] Retrying in {wait_sec}s...", flush=True)
                    time.sleep(wait_sec)
                    continue
                return "", f"Azure HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}"
            except Exception as e:
                return "", f"Azure error: {e}"
        return "", "Azure TTS failed after multiple retries due to throttling (429)."
    else:
        payload = {
            "input": {"text": text},
            "voice": _voice_payload(voice),
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.92, "pitch": -1.0, "volumeGainDb": 4.0},
        }
        req = urllib.request.Request(
            TTS_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8")).get("audioContent", ""), ""
        except urllib.error.HTTPError as e:
            return "", f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}"
        except Exception as e:
            return "", str(e)

def tts_with_fallbacks(text: str, voices: list[dict]) -> str:
    snippet = text[:50].replace("\n", " ")
    lc = voices[0].get("languageCode", "?")
    print(f"  -> [{lc}] {snippet!r}...", flush=True)
    for i, v in enumerate(voices):
        b64, err = tts_one(text, v)
        if b64:
            if i > 0:
                print(f"      (ok: {v.get('name', lc)})", flush=True)
            return b64
        short = err.replace("\n", " ")[:180]
        print(f"      • {v.get('name', lc)}: {short}", flush=True)
    print(f"  [ERROR] TTS failed after {len(voices)} voices.", flush=True)
    return ""

def audio_filename(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16] + ".mp3"

# ──────────────────────────────────────────
# COLLECT SPEAKABLE STRINGS
# ──────────────────────────────────────────

def collect_strings(node) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k in SKIP_KEYS:
                continue
            found |= collect_strings(v)
    elif isinstance(node, list):
        for item in node:
            found |= collect_strings(item)
    elif isinstance(node, str) and node.strip():
        found.add(node)
    return found

# ──────────────────────────────────────────
# WRITE HELPERS
# ──────────────────────────────────────────

def write_audio_index(path: Path, mapping: dict[str, str]) -> None:
    body = (
        "// Auto-generated — do not edit by hand\n"
        "window.__lessonAudioIndex = "
        + json.dumps(mapping, ensure_ascii=False, indent=2)
        + ";\n"
        + 'window.__lessonAudioMime = "audio/mp3";\n'
    )
    path.write_text(body, encoding="utf-8")

def write_lesson_data_js(path: Path, locales: dict) -> None:
    root = {
        "defaultLocale": "en",
        "supportedLocales": ["en", "hi", "ja", "as"],
        "localeLabels": {"en": "English", "hi": "हिंदी", "ja": "日本語", "as": "অসমীয়া"},
        "locales": locales
    }
    body = (
        "// Auto-generated — do not edit by hand\n"
        "window.__lessonData = "
        + json.dumps(root, ensure_ascii=False, indent=2)
        + ";\n"
    )
    path.write_text(body, encoding="utf-8")

# ──────────────────────────────────────────
# MAIN BUILD
# ──────────────────────────────────────────

def build_audio(locale_pack: dict, loc: str, out_dir: Path) -> None:
    cfg = LOCALE_TTS.get(loc)
    if not cfg:
        print(f"  No TTS voice for locale {loc!r}, skipping audio.", flush=True)
        return
    voices: list[dict] = cfg if isinstance(cfg, list) else [cfg]

    strings = sorted(collect_strings(locale_pack), key=len)
    print(f"\nLocale {loc}: {len(strings)} strings to synthesise", flush=True)

    audio_subdir = out_dir / "audio" / loc
    audio_subdir.mkdir(parents=True, exist_ok=True)

    index_map: dict[str, str] = {}
    reused = 0

    for text in strings:
        fname = audio_filename(text)
        fpath = audio_subdir / fname
        rel = f"audio/{loc}/{fname}"
        if fpath.exists() and fpath.stat().st_size > 0:
            index_map[text] = rel
            reused += 1
            continue
        b64 = tts_with_fallbacks(text, voices)
        if b64:
            fpath.write_bytes(base64.b64decode(b64))
            index_map[text] = rel

    index_file = out_dir / f"audio_index_{loc}.js"
    write_audio_index(index_file, index_map)
    print(f"  Saved {len(index_map)} clips -> audio/{loc}/  ({reused} reused); wrote {index_file.name}", flush=True)

def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Build i18n lesson data + audio dynamically")
    parser.add_argument("--only", type=str, default=None,
                        help="Comma-separated locale codes, e.g. en,hi")
    args = parser.parse_args()

    only_set: set[str] | None = None
    if args.only:
        only_set = {x.strip() for x in args.only.split(",") if x.strip()}

    target_locales = ["en", "hi", "ja", "as"]
    if only_set:
        target_locales = [l for l in target_locales if l in only_set]

    # Validate environment keys
    if "as" in target_locales and not os.environ.get("AZURE_TTS_API_KEY"):
        print("ERROR: Set AZURE_TTS_API_KEY environment variable for Assamese TTS.", flush=True)
        raise SystemExit(1)
    
    needs_google_tts = bool(set(target_locales) - {"as"})
    if needs_google_tts and not TTS_KEY:
        print("ERROR: Set GOOGLE_TTS_API_KEY environment variable.", flush=True)
        raise SystemExit(1)
        
    needs_translate = bool(set(target_locales) - {"en"})
    if needs_translate and not TRANSLATE_KEY:
        print("ERROR: Set GOOGLE_TRANSLATION_API_KEY (or GOOGLE_TTS_API_KEY) environment variable.", flush=True)
        raise SystemExit(1)

    lesson_data_path = OUT_DIR / "lesson_data.js"
    if not lesson_data_path.exists():
        print(f"ERROR: {lesson_data_path} not found. Make sure the script is run in its containing folder.", flush=True)
        raise SystemExit(1)

    # Load English data from existing lesson_data.js
    try:
        existing_txt = lesson_data_path.read_text(encoding="utf-8")
        start = existing_txt.index("{")
        end = existing_txt.rindex("}") + 1
        existing_root = json.loads(existing_txt[start:end])
        en_data = existing_root["locales"]["en"]
    except Exception as e:
        print(f"ERROR: Could not parse existing lesson_data.js: {e}", flush=True)
        raise SystemExit(1)

    # 1. Build locale data
    locales: dict = {}
    for loc in ["en", "hi", "ja", "as"]:
        if only_set and loc not in only_set:
            continue
        if loc == "en":
            locales["en"] = deepcopy(en_data)
        else:
            locales[loc] = _build_locale_preserving(en_data, loc, LOCALE_TRANSLATE_CODES[loc], LESSON_DATA_PATH_FOR_MERGE)

    # Merge existing locales that we didn't translate in this run
    if only_set:
        for loc, pack in existing_root.get("locales", {}).items():
            if loc not in locales:
                locales[loc] = pack

    # 2. Write lesson_data.js
    print(f"\nWriting lesson_data.js ({list(locales.keys())})...", flush=True)
    write_lesson_data_js(lesson_data_path, locales)
    print(f"  -> {lesson_data_path}", flush=True)

    # 3. Synthesise audio for each locale
    for loc in target_locales:
        pack = locales.get(loc)
        if not pack:
            print(f"\nSkip audio for {loc} (locale data not built)", flush=True)
            continue
        build_audio(pack, loc, OUT_DIR)

    print("\nDone!", flush=True)

if __name__ == "__main__":
    main()
