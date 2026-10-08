"""fieldnotes: voice/text nature notes grounded to a local species shortlist."""
import argparse, datetime, glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
JOURNAL = os.path.join(HERE, "journal.json")
MODEL = os.environ.get("FIELDNOTES_MODEL", "gemma3:1b")
MAX_S = 20


def regions():
    return sorted(os.path.basename(p)[8:-5] for p in glob.glob(os.path.join(DATA_DIR, "species_*.json")))


def load_species(region):
    region = (region or "").lower()
    path = os.path.join(DATA_DIR, f"species_{region}.json")
    if not os.path.exists(path):
        sys.exit(f"Error: unknown region '{region}'. Available: {', '.join(regions()) or 'none'}. "
                 "Add data/species_<region>.json to add a region.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def tok(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def score(transcript, sp):
    pool = sp["category"] + " " + sp["habitat"] + " " + " ".join(sp["key_features"])
    return len(tok(transcript) & tok(pool))


def shortlist(transcript, all_sp, hi=8, lo=6):
    ranked = sorted(all_sp, key=lambda s: (-score(transcript, s), s["id"]))
    hits = [s for s in ranked if score(transcript, s) > 0][:hi]
    return hits if len(hits) >= lo else ranked[:lo]


def enforce(cands, short_ids):
    kept = [c for c in cands if c.get("id") in set(short_ids)]
    return kept, len(kept) != len(cands)


RANK_CONF = (0.6, 0.3, 0.1)
FALLBACK_Q = "What colour is it, and what is it doing?"


def rank(cands):
    return sorted(cands, key=lambda c: -c["confidence"])


def resolve_conf(items):
    vals = []
    for c in items[:3]:
        c = {"id": c} if isinstance(c, str) else c
        if not isinstance(c, dict) or not c.get("id"):
            continue
        try:
            v = float(c.get("confidence"))
        except (TypeError, ValueError):
            v = None
        vals.append((str(c["id"]), v))
    if not vals:
        raise ValueError("no candidates with ids")
    given = [v for _, v in vals]
    if any(v is None for v in given) or (len(given) > 1 and len(set(given)) == 1):
        return [{"id": i, "confidence": RANK_CONF[k]} for k, (i, _) in enumerate(vals)], "rank"
    return [{"id": i, "confidence": max(0.0, min(1.0, v))} for i, v in vals], "model"


def followup(short, cands):
    by_id = {s["id"]: set(s["key_features"]) for s in short}
    feats = [by_id.get(c["id"], set()) for c in cands[:2]]
    if len(feats) == 2 and feats[0] ^ feats[1]:
        return f"Does it have: {sorted(feats[0] ^ feats[1])[0]}?"
    return FALLBACK_Q


def identify(transcript, short):
    try:
        import ollama
    except ImportError:
        sys.exit("Error: pip package 'ollama' not installed.")
    mini = [{k: s[k] for k in ("id", "common_name", "category", "key_features", "habitat")} for s in short]
    prompt = ("Pick the TOP 3 species from SHORTLIST only that best match the TRANSCRIPT. "
              "Reply ONLY JSON: {\"candidates\": [{\"id\": str, \"confidence\": 0-1} x3], "
              f"\"followup\": str}}.\nTRANSCRIPT: {transcript}\nSHORTLIST: {json.dumps(mini)}")
    t0 = time.time()
    try:
        r = ollama.chat(model=MODEL, messages=[{"role": "user", "content": prompt}], format="json")
    except Exception as e:
        sys.exit(f"Error: cannot reach Ollama ({e}). Is `ollama serve` running, "
                 f"model '{MODEL}' pulled? (env FIELDNOTES_MODEL)")
    dt = round(time.time() - t0, 2)
    try:
        raw = json.loads(r["message"]["content"])
        cands, src = resolve_conf(raw.get("candidates", []))
    except Exception as e:
        sys.exit(f"Error: bad model JSON ({e}).")
    kept, viol = enforce(cands, [s["id"] for s in short])
    kept = rank(kept)
    ans = {"candidates": kept, "followup": followup(short, kept), "grounding_violation": viol}
    return ans, dt, src


def append_entry(entry):
    js = []
    if os.path.exists(JOURNAL):
        try:
            with open(JOURNAL, encoding="utf-8") as f:
                js = json.load(f)
        except (json.JSONDecodeError, ValueError):
            sys.exit("Error: journal.json is corrupt.")
    js.append(entry)
    with open(JOURNAL, "w", encoding="utf-8") as f:
        json.dump(js, f, indent=2)
    return len(js)


def save_note(transcript, region):
    all_sp = load_species(region)
    short = shortlist(transcript, all_sp)
    ids = [s["id"] for s in short]
    print(f"Region: {region}")
    print("Shortlist:", ", ".join(f"{s['id']} ({s['common_name']})" for s in short))
    ans, dt, src = identify(transcript, short)
    for c in ans["candidates"]:
        print(f"  {c['id']} conf={c['confidence']:.2f}")
    if ans["grounding_violation"]:
        print("WARNING: model cited id(s) outside shortlist; dropped (grounding_violation).")
    print("Follow-up:", ans["followup"])
    top = ans["candidates"][0]["id"] if ans["candidates"] else "none"
    top3 = [c["id"] for c in ans["candidates"]]
    while True:
        try:
            u = input(f"Type the correct id {top3} or 'none': ").strip()
        except EOFError:
            u = "none"
        if u:
            break
    entry = {"timestamp": datetime.datetime.now().astimezone().isoformat(), "transcript": transcript,
             "region": region, "shortlist": ids, "model_answer": ans, "confirmed_label": u,
             "correct": bool(ans["candidates"] and u == top), "in_top3": u in top3,
             "in_shortlist": u in ids, "confidence_source": src, "latency_s": dt}
    print(f"Saved ({append_entry(entry)} entries). correct={entry['correct']}")


def cmd_listen(_a):
    import threading
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        sys.exit("Error: install sounddevice + numpy.")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("Error: install faster-whisper.")
    stop = threading.Event()
    threading.Thread(target=lambda: (sys.stdin.readline(), stop.set()), daemon=True).start()
    print(f"Recording... press Enter to stop (max {MAX_S}s).")
    chunks, t0 = [], time.time()
    try:
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32") as st:
            while not stop.is_set() and time.time() - t0 < MAX_S:
                n = st.read(1600)[0]
                chunks.append(n.copy())
    except Exception as e:
        sys.exit(f"Error: microphone failed ({e}).")
    if not chunks:
        sys.exit("Error: no audio recorded.")
    audio = np.concatenate(chunks, axis=0).flatten()
    print("Transcribing locally (base.en)...")
    segs, _ = WhisperModel("base.en", device="cpu", compute_type="int8").transcribe(audio, beam_size=5)
    text = "".join(s.text for s in segs).strip()
    print("Transcript:", text or "(empty)")
    if text:
        save_note(text, _a.region)


def cmd_text(a):
    if not a.text.strip():
        sys.exit("Error: empty text.")
    save_note(a.text.strip(), a.region)


def cmd_stats(_a):
    js = json.load(open(JOURNAL, encoding="utf-8")) if os.path.exists(JOURNAL) else []
    n = len(js)
    t1 = sum(1 for e in js if e.get("correct"))
    t3 = sum(1 for e in js if e.get("in_top3"))
    cov = sum(1 for e in js if e.get("in_shortlist"))
    viols = sum(1 for e in js if e.get("model_answer", {}).get("grounding_violation"))
    if n:
        print(f"entries: {n}\ntop-1 hit rate: {t1}/{n} = {t1 / n:.2f}"
              f"\ntop-3 hit rate: {t3}/{n} = {t3 / n:.2f}"
              f"\nshortlist coverage: {cov}/{n} = {cov / n:.2f}"
              f"\ngrounding violations: {viols}")
    else:
        print("entries: 0")


def main():
    p = argparse.ArgumentParser(prog="fieldnotes")
    p.add_argument("--region", default=os.environ.get("FIELDNOTES_REGION", "gujarat"),
                   help="species list to use (data/species_<region>.json)")
    sub = p.add_subparsers(dest="cmd", required=True)
    li = sub.add_parser("listen")
    t = sub.add_parser("text")
    t.add_argument("text")
    st = sub.add_parser("stats")
    for sp in (li, t, st):  # also accept --region after the subcommand
        sp.add_argument("--region", default=argparse.SUPPRESS)
    a = p.parse_args()
    {"listen": cmd_listen, "text": cmd_text, "stats": cmd_stats}[a.cmd](a)


if __name__ == "__main__":
    main()
