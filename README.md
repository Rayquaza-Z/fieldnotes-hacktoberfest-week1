# 🌿 Fieldnotes

**Speak to it outside. It tells you what you just saw — with no internet, no account, no cloud.**

Fieldnotes is a voice-first nature journal for birds, plants, and insects. Tap the
microphone, describe what you see, and a local open-weight model (Gemma) identifies
it from a grounded regional shortlist. Every sighting is saved with GPS, so your
journal becomes a map of where you've been.

![Fieldnotes demo](docs/demo.gif)

| Laptop | Mobile |
|---|---|
| ![Desktop UI](docs/ui-desktop.png) | ![Mobile UI](docs/ui-mobile.png) |

*Screenshots rendered from the real running app (headless Chromium); the GIF shows
the typed flow — the mic flow is identical after tapping the orb.*

## Why open matters here

A nature app is useless if it needs a signal — the whole point is being somewhere
with no bars. So everything runs on your own machine:

- **faster-whisper** transcribes your voice on-device, nothing uploaded.
- **Ollama + Gemma** (`gemma3:1b`) identifies locally, costs nothing, works offline.
- Swap the model with `FIELDNOTES_MODEL`, add your region with one JSON file —
  no permission, no API key, no vendor.

## How it works

```
voice ──▶ faster-whisper (base.en, local) ──▶ transcript
                                                   │
text ─────────────────────────────────────────────┘
                                                   ▼
                        keyword shortlist (6–8 species, local JSON)
                                                   ▼  (only transcript + shortlist leave the app)
                        Ollama/Gemma ──▶ top 3, confidence-sorted, grounding-checked
                                                   ▼
                        code-written follow-up ("Does it have: …?")
                                                   ▼
                        you tap the right one ──▶ journal.json (+ GPS, device, latency)
```

Two guardrails keep the model honest: any species id outside the shortlist is
dropped and flagged as a `grounding_violation`, and flat/missing confidences are
replaced with rank-based `0.6 / 0.3 / 0.1` scores (marked `"confidence_source": "rank"`).

## For non-technical users

1. Someone technical does the one-time setup below (and `ollama serve`).
2. Double-click **`start-fieldnotes.bat`** — Fieldnotes opens in the browser.
3. Tap the microphone and speak (or expand *"or describe it in words"* to type).
4. Tap the right species — or *None of these*. Done, it's logged.

On a phone, use **Add to Home Screen**: the page is an installable offline app
(manifest + service worker + procedurally generated icons, zero dependencies).
It detects mobile vs laptop itself, GPS-tags entries, and tells you whether
you're inside Gujarat.

## For developers

```bat
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install faster-whisper sounddevice numpy ollama
ollama serve
ollama pull gemma3:1b

.\.venv\Scripts\python.exe app.py            & :: browser UI at http://127.0.0.1:8765
.\.venv\Scripts\python.exe fieldnotes.py listen --region gujarat
.\.venv\Scripts\python.exe fieldnotes.py text "green parrot with red beak" --region gujarat
.\.venv\Scripts\python.exe fieldnotes.py stats
.\.venv\Scripts\python.exe -m unittest -v     & :: 15 tests
```

Options: `--region` (default `gujarat`, `FIELDNOTES_REGION` fallback),
`FIELDNOTES_MODEL` (default `gemma3:1b`). Unknown regions exit listing what's
available — adding a region is one file: `data/species_<name>.json` with
`id, common_name, category, key_features (4–6 phrases), habitat`.

## Project layout

```
fieldnotes.py          CLI + scoring, grounding, confidence, follow-up, journal (216 lines)
app.py                 stdlib-only web UI: voice upload, PWA, PNG icons, GPS, device modes
start-fieldnotes.bat   double-click launcher
data/species_gujarat.json   50 Surat-area birds, plants, insects
test_fieldnotes.py     15 unittest tests (scoring, grounding, regions, follow-up, confidence, ranking)
docs/                  real screenshots + demo GIF (captured headless, see docs note below)
```

*`docs/` images are generated, not fragile fixtures — delete and re-capture any
time with Playwright against the running app.*

## Built for Hacktoberfest 2026 — Touch Grass 🌾

Made for the DEV *Hacktoberfest Open-Source AI Challenge: Week 1*. Open weights
at the core, on-device inference throughout, and the screen is the shortest part
of the experience: go outside, tap the mic, log a sparrow.
