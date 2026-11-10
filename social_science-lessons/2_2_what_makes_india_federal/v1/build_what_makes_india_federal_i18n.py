"""
build_what_makes_india_federal_i18n.py

Builds lesson_data.js (with en + hi + ja locales) and audio_index_*.js files
for the 2_federalism/2_2_what_makes_india_federal/ lesson.

Usage:
  python "2_federalism/build_what_makes_india_federal_i18n.py"
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

# Look for .env in script dir AND parent dir (project root)
def _load_env():
    here = Path(__file__).resolve().parent
    # Walk every ancestor: lessons sit 4+ levels below the project root,
    # so a fixed 2-level search cannot reach .env.
    for candidate in [p / ".env" for p in [here, *here.parents]]:
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
TRANSLATE_KEY = os.environ.get("GOOGLE_TRANSLATION_API_KEY", "") or TTS_KEY  # fallback to same key
API_KEY = TTS_KEY  # kept for compat
TTS_URL = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={TTS_KEY}"
TRANSLATE_URL = f"https://translation.googleapis.com/language/translate/v2?key={TRANSLATE_KEY}"

OUT_DIR = Path(__file__).resolve().parent

LOCALE_TTS = {
    "en": {"languageCode": "en-IN", "name": "en-IN-Chirp3-HD-Aoede"},
    "hi": [
        {"languageCode": "hi-IN", "name": "hi-IN-Wavenet-A", "ssmlGender": "FEMALE"},
        {"languageCode": "hi-IN", "name": "hi-IN-Standard-A", "ssmlGender": "FEMALE"},
    ],
    "ja": [
        {"languageCode": "ja-JP", "name": "ja-JP-Neural2-B", "ssmlGender": "FEMALE"},
        {"languageCode": "ja-JP", "name": "ja-JP-Wavenet-B", "ssmlGender": "FEMALE"},
        {"languageCode": "ja-JP", "name": "ja-JP-Standard-A"},
        {"languageCode": "ja-JP", "name": "ja-JP-Standard-B"},
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

SKIP_KEYS = frozenset({"icon", "bgClass", "type", "correct"})

# ──────────────────────────────────────────
# ENGLISH SOURCE DATA
# ──────────────────────────────────────────
EN_DATA = {
    "documentTitle": "What Makes India Federal — Class 10 Political Science",
    "welcome": {
        "badge": "NCERT",
        "badgeSub": "Class 10 · Political Science",
        "label": "Class 10 Political Science • Chapter 2",
        "title": "What Makes India Federal?",
        "subtitle": "Explore the constitutional design that divides power in the world's largest democracy — the three lists, special provisions, and the role of the judiciary.",
        "beginButton": "Begin Learning",
        "welcomeSpeech": "Welcome to the section — What Makes India Federal? In this section, we explore the constitutional design that divides power in the world's largest democracy — the three lists, special provisions, and the role of the judiciary. Press Begin Learning when you are ready."
    },
    "ui": {
        "revealButton": "Discover the Answer",
        "exerciseLabel": "Test Your Understanding",
        "testUnderstandingPrefix": "Test your understanding. ",
        "feedbackCorrectPrefix": "Excellent! That's correct. ",
        "feedbackIncorrectPrefix": "Not quite right. ",
        "sectionCompleteLabel": "Section Complete",
        "completeTitles": ["Excellent!", "Well Done!", "Outstanding!"],
        "nextTopicButton": "Continue",
        "reviewAgainButton": "Review Again",
        "finalLabel": "Section Complete",
        "finalTitle": "Outstanding!",
        "finalSubtitle": "You now understand India's federal structure — the three lists, special provisions, and how the Constitution protects this power-sharing arrangement.",
        "startAgainButton": "Start Again",
        "finalSpeech": "Congratulations! You have completed this section. You now understand India's federal structure, the three lists, special provisions, and how the Constitution protects this power-sharing arrangement."
    },
    "sidebar": {
        "completed": "Completed",
        "inProgress": "In Progress"
    },
    "sections": [
        {"name": "Three Lists", "status": "Union · State · Concurrent"},
        {"name": "Special Provisions", "status": "Article 371 & Union Territories"},
        {"name": "Three Tiers", "status": "Local Government"},
        {"name": "Revenue & Taxes", "status": "Financial Autonomy"}
    ],
    "lessons": [
        {
            "question": "How does the Indian Constitution divide power between the Union and State governments? What subjects can each level legislate on?",
            "label": "Three Lists",
            "completeMsg": "The Indian Constitution provides a three-fold distribution of legislative powers: the Union List (national importance), the State List (state importance), and the Concurrent List (both). In case of conflict on Concurrent subjects, Union law prevails.",
            "steps": [
                {"text": "The Indian Constitution provides a three-fold distribution of legislative powers through three lists. The Union List includes subjects of national importance like defence, foreign affairs, banking, and currency — only the Union government can make laws on these. The State List covers subjects like police, trade, agriculture, and irrigation — only states can legislate here."},
                {"text": "For subjects not in any list — like computer software — the Union government has the power to legislate. These are called residuary subjects. This three-list system ensures clear boundaries while allowing flexibility for new challenges."}
            ],
            "exercise": {
                "question": "A new subject like \"cyber security\" that is not in any of the three lists would be legislated by:",
                "options": [
                    "State Government only",
                    "Both Union and State equally",
                    "Union Government (residuary powers)",
                    "Local Government"
                ],
                "correct": 2,
                "explanation": "Subjects not in any of the three lists fall under residuary powers, which are held by the Union Government. This ensures the central government can address new and emerging issues."
            },
            "canvas": {
                "title1": "The Three Lists",
                "unionTitle": "UNION LIST",
                "unionSub": "🏛️ Only Centre",
                "union1": "🛡️ Defence",
                "union2": "🌐 Foreign Affairs",
                "union3": "🏦 Banking",
                "union4": "💱 Currency",
                "union5": "📡 Communications",
                "stateTitle": "STATE LIST",
                "stateSub": "🏢 Only States",
                "state1": "👮 Police",
                "state2": "📊 Trade",
                "state3": "🌾 Agriculture",
                "state4": "💧 Irrigation",
                "state5": "🏥 Health",
                "concurrentTitle": "CONCURRENT",
                "concurrentSub": "🤝 Both levels",
                "concurrent1": "📚 Education",
                "concurrent2": "🌲 Forests",
                "concurrent3": "👷 Trade Unions",
                "concurrent4": "💒 Marriage",
                "concurrent5": "📝 Adoption",
                "conflictAlert": "If laws conflict on Concurrent subjects → Union law prevails",
                "title2": "Residuary Subjects",
                "questionLabel": "What if a subject is NOT in any list?",
                "softwareLabel": "💻 Computer Software?",
                "notInLists": "Not in Union, State, or Concurrent List",
                "unionDecides": "→ UNION GOVERNMENT decides",
                "residuarySub": "These are 'residuary' subjects",
                "adaptLabel": "This ensures the system can adapt to modern challenges",
                "boundariesLabel": "while maintaining clear federal boundaries"
            }
        },
        {
            "question": "Do all states in India have identical powers? What about areas that are too small to be states?",
            "label": "Special Provisions",
            "completeMsg": "Not all states have equal powers: some enjoy special powers under Article 371, while tiny territories become Union Territories run directly by the Centre. Amendments to this system require Parliament's two-thirds majority and ratification by half the states.",
            "steps": [
                {"text": "Not all states have equal powers. States like Assam, Nagaland, Arunachal Pradesh, and Mizoram enjoy special powers under Article 371 due to their unique social and historical circumstances. These include protection of indigenous land rights, culture, and preferential employment. Some areas are too small to be states but cannot merge with existing ones — these become Union Territories."},
                {"text": "The power-sharing arrangement is protected by the Constitution. Parliament alone cannot change it — any amendment needs a two-thirds majority in both Houses, plus ratification by at least half the state legislatures. The judiciary — High Courts and Supreme Court — settles disputes between levels of government."}
            ],
            "exercise": {
                "question": "To change the power-sharing arrangement between Centre and States, what is required?",
                "options": [
                    "Simple majority in Parliament",
                    "Two-thirds majority in Parliament + ratification by half the state legislatures",
                    "Approval of the President alone",
                    "A national referendum"
                ],
                "correct": 1,
                "explanation": "Changing the federal power-sharing arrangement requires a two-thirds majority in both Houses of Parliament AND ratification by the legislatures of at least half of the total States."
            },
            "canvas": {
                "title1": "Unequal Powers in Indian Federation",
                "regularStatesTitle": "Regular States",
                "regularStatesLine1": "Standard powers under",
                "regularStatesLine2": "the Constitution",
                "specialStatesTitle": "⭐ Special Status States",
                "specialStatesLine1": "Assam, Nagaland,",
                "specialStatesLine2": "Arunachal Pradesh, Mizoram",
                "specialStatesSub": "Article 371",
                "utTitle": "Union Territories",
                "utLine1": "Chandigarh • Lakshadweep • Delhi",
                "utLine2": "Central Govt has special powers here",
                "title2": "Protecting Federal Structure",
                "changeLabel": "To change power-sharing arrangements:",
                "step1Label": "Step 1: ⅔ majority in BOTH Houses of Parliament",
                "step2Label": "Step 2: Ratified by ½ of State legislatures",
                "umpireTitle": "⚖️ Judiciary as Umpire",
                "umpireLine1": "High Courts & Supreme Court settle",
                "umpireLine2": "disputes between levels of government"
            }
        },
        {
            "question": "India originally had two tiers of government. What was the third tier added later, and why?",
            "label": "Three Tiers",
            "completeMsg": "A third tier of federalism was added in the form of Panchayats (rural local bodies) and Municipalities (urban local bodies) to deepen democracy at the grassroots level.",
            "steps": [
                {"text": "The Constitution originally provided for two tiers — the Union Government and State Governments. Later, a third tier was added in the form of Panchayats and Municipalities, giving India a three-level federal structure. Union Territories like Delhi, Chandigarh, and Lakshadweep have a special arrangement where the central government has more direct control."}
            ],
            "exercise": {
                "question": "The third tier of Indian federalism consists of:",
                "options": [
                    "High Courts and Supreme Court",
                    "Union Territories",
                    "Panchayats and Municipalities",
                    "Regional political parties"
                ],
                "correct": 2,
                "explanation": "The third tier of Indian federalism is Panchayats (rural) and Municipalities (urban) — local government bodies that were given constitutional status to deepen democracy at the grassroots level."
            },
            "canvas": {
                "title": "India's Three-Tier Structure",
                "tier1Title": "🏛️ Tier 1: UNION GOVERNMENT",
                "tier2Title": "🏢 Tier 2: STATE GOVERNMENTS",
                "tier3Title": "🏘️ Tier 3: PANCHAYATS & MUNICIPALITIES",
                "tier3Sub": "Third tier added later → strengthened democracy at grassroots"
            }
        },
        {
            "question": "How do both the Union and State Governments fund themselves? Can one level depend entirely on the other for money?",
            "label": "Revenue & Taxes",
            "completeMsg": "Each tier of government is constitutionally empowered to levy specific taxes. This financial autonomy ensures that states are not financially dependent on the Union, preserving the federal balance.",
            "steps": [
                {"text": "Both levels of government have the power to raise resources by levying taxes. The Union Government collects income tax, customs duty, and GST, while State Governments collect taxes on agricultural income, stamp duty, and vehicle tax. This financial autonomy is essential — if one level depended on the other for funds, it could not function independently."}
            ],
            "exercise": {
                "question": "Why is it important that both levels of government have their own revenue sources?",
                "options": [
                    "So the Union can control States through funding",
                    "To ensure financial autonomy and true independence",
                    "Because the Constitution requires it symbolically",
                    "To increase total government revenue"
                ],
                "correct": 1,
                "explanation": "Each level of government needs its own revenue sources to ensure financial autonomy. Without independent funding, a level of government would be dependent on the other and could not truly function as an independent tier of the federation."
            },
            "canvas": {
                "title": "Financial Autonomy",
                "unionRevTitle": "Union Revenue",
                "unionRev1": "💵 Income Tax",
                "unionRev2": "🚢 Customs Duty",
                "unionRev3": "🏭 GST (central)",
                "unionRev4": "📊 Corporate Tax",
                "stateRevTitle": "State Revenue",
                "stateRev1": "🌾 Agriculture Tax",
                "stateRev2": "📜 Stamp Duty",
                "stateRev3": "🚗 Vehicle Tax",
                "stateRev4": "🏭 GST (state)",
                "financialInd": "💡 Financial independence = True federal autonomy"
            }
        }
    ]
}

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

def build_locale(target_lang: str) -> dict:
    """Build a translated locale pack from EN_DATA."""
    print(f"\nTranslating to {target_lang}...", flush=True)
    return translate_node(deepcopy(EN_DATA), target_lang)

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

def _audio_config(voice: dict) -> dict:
    """MP3 config. Chirp3-HD voices reject `pitch`, so omit it for those."""
    cfg = {"audioEncoding": "MP3", "speakingRate": 0.92, "volumeGainDb": 4.0}
    if "Chirp3-HD" not in voice.get("name", ""):
        cfg["pitch"] = -1.0
    return cfg

def tts_one(text: str, voice: dict) -> tuple[str, str]:
    """Returns (base64_mp3_or_empty, error_or_empty)."""
    import time
    lang_code = voice.get("languageCode", "")
    if lang_code.startswith("as"):
        azure_key = os.environ.get("AZURE_TTS_API_KEY", "").strip()
        if not azure_key:
            return "", "AZURE_TTS_API_KEY not found in environment"
        region = "eastus"
        url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        # Azure needs valid XML: a bare & (or < >) in the text makes the
        # whole SSML payload invalid and the request fails with HTTP 400.
        import html as _html
        _safe = _html.escape(text, quote=False)
        ssml = f"""<speak version='1.0' xml:lang='{lang_code}'>
            <voice name='{voice.get("name", "as-IN-YashicaNeural")}'>
                {_safe}
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
                # Add a tiny base delay to avoid hammering the API
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
            "audioConfig": _audio_config(voice),
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
        "// Auto-generated by build_what_makes_india_federal_i18n.py — do not edit by hand\n"
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
        "// Auto-generated by build_what_makes_india_federal_i18n.py — do not edit by hand\n"
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

    parser = argparse.ArgumentParser(description="Build What Makes India Federal i18n lesson data + audio")
    parser.add_argument("--only", type=str, default=None,
                        help="Comma-separated locale codes, e.g. en,hi")
    args = parser.parse_args()

    only_set: set[str] | None = None
    if args.only:
        only_set = {x.strip() for x in args.only.split(",") if x.strip()}

    target_locales = ["en", "hi", "ja", "as"]
    if only_set:
        target_locales = [l for l in target_locales if l in only_set]

    needs_tts = bool(target_locales)
    needs_translate = bool(set(target_locales) - {"en"})
    if needs_tts and not TTS_KEY:
        print("ERROR: Set GOOGLE_TTS_API_KEY environment variable.", flush=True)
        raise SystemExit(1)
    if "as" in target_locales and not os.environ.get("AZURE_TTS_API_KEY"):
        print("ERROR: Set AZURE_TTS_API_KEY environment variable for Assamese TTS.", flush=True)
        raise SystemExit(1)
    if needs_translate and not TRANSLATE_KEY:
        print("ERROR: Set GOOGLE_TRANSLATION_API_KEY (or GOOGLE_TTS_API_KEY) environment variable.", flush=True)
        raise SystemExit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Build locale data
    locales: dict = {}
    for loc in ["en", "hi", "ja", "as"]:
        if only_set and loc not in only_set:
            continue
        if loc == "en":
            locales["en"] = deepcopy(EN_DATA)
        else:
            locales[loc] = _build_locale_preserving(EN_DATA, loc, LOCALE_TRANSLATE_CODES[loc], LESSON_DATA_PATH_FOR_MERGE)

    # If we only built a subset, load existing lesson_data.js to merge
    lesson_data_path = OUT_DIR / "lesson_data.js"
    if only_set and lesson_data_path.exists():
        try:
            existing_txt = lesson_data_path.read_text(encoding="utf-8")
            # Extract JSON from window.__lessonData = {...};
            start = existing_txt.index("{")
            end = existing_txt.rindex("}") + 1
            existing_root = json.loads(existing_txt[start:end])
            for loc, pack in existing_root.get("locales", {}).items():
                if loc not in locales:
                    locales[loc] = pack
        except Exception as e:
            print(f"  [WARN] Could not merge existing lesson_data.js: {e}", flush=True)

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
