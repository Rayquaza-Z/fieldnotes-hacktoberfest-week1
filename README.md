# fieldnotes

Voice/text nature notes, grounded to a local species shortlist. Transcription is local
(faster-whisper `base.en`); identification uses local Ollama (`FIELDNOTES_MODEL`,
default `gemma3:1b`).

## Usage

```bat
.\.venv\Scripts\python.exe fieldnotes.py listen [--region gujarat]
.\.venv\Scripts\python.exe fieldnotes.py text "green parrot with red beak" --region gujarat
.\.venv\Scripts\python.exe fieldnotes.py stats
.\.venv\Scripts\python.exe -m unittest -v
```

## Regions

`--region` (default `gujarat`, env `FIELDNOTES_REGION` fallback) selects
`data/species_<region>.json`. Unknown regions exit with the available list.
Adding a new region means adding one JSON file with the same schema
(`id, common_name, category, key_features, habitat`), e.g.
`data/species_rajasthan.json` — no code changes needed.
