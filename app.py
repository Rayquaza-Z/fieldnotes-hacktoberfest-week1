"""Local web UI for fieldnotes (standard library only, works offline).

Run: .\.venv\Scripts\python.exe app.py  -> opens http://127.0.0.1:8765 in your browser.
"""
import datetime
import json
import os
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import fieldnotes as fn

PORT = 8765
MAX_REC_S = 20

MANIFEST = {"name": "Fieldnotes", "short_name": "Fieldnotes", "start_url": "/",
            "display": "standalone", "background_color": "#f6f4ec", "theme_color": "#4c6b4f",
            "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                      {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}]}

SW = """const C = 'fieldnotes-v1';
const ASSETS = ['/', '/manifest.json', '/icon-192.png', '/icon-512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(C).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(caches.match(e.request).then(hit => {
    const net = fetch(e.request).then(r => {
      if (r.ok) caches.open(C).then(c => c.put(e.request, r.clone()));
      return r;
    }).catch(() => hit);
    return hit || net;
  }));
});
"""


def png_icon(px):
    """Procedural app icon (sage disc + voice bars), pure stdlib PNG."""
    import struct
    import zlib
    cx = cy = px / 2
    r = px * 0.32
    bars = [(-0.13, 0.10), (0.0, 0.17), (0.13, 0.10)]
    raw = bytearray()
    for y in range(px):
        raw.append(0)
        for x in range(px):
            dx, dy = x - cx + 0.5, y - cy + 0.5
            if dx * dx + dy * dy <= r * r:
                hit = any(abs(dx - ox * px) <= 0.028 * px and abs(dy) <= h * px / 2
                          for ox, h in bars)
                raw += bytes((76, 107, 79) if hit else (246, 244, 236))
            else:
                raw += bytes((76, 107, 79))

    def chunk(tag, data):
        head = tag + data
        return struct.pack(">I", len(data)) + head + struct.pack(">I", zlib.crc32(head))

    ihdr = struct.pack(">IIBBBBB", px, px, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fieldnotes</title>
<meta name="theme-color" content="#4c6b4f">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/icon-192.png">
<style>
:root{
  --paper:#f6f4ec; --card:#fffdf7; --ink:#2c2a24; --muted:#8b8474;
  --sage:#4c6b4f; --sage-deep:#33482f; --line:#e4dfcf; --rec:#c05b4d;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
  min-height:100vh;display:flex;flex-direction:column;align-items:center}
main{width:100%;max-width:560px;padding:2.5em 1.5em 1em;text-align:center}
.brand{font-family:Georgia,'Times New Roman',serif;font-size:1.9em;letter-spacing:.02em;margin:0}
.tag{color:var(--muted);font-size:.9em;margin:.3em 0 1.4em}
.pills{display:flex;gap:.4em;justify-content:center;margin-bottom:2.2em;flex-wrap:wrap}
.pill{border:1px solid var(--line);background:transparent;color:var(--muted);
  border-radius:999px;padding:.3em 1em;font-size:.82em;cursor:pointer;text-transform:capitalize}
.pill.on{background:var(--sage);border-color:var(--sage);color:#fff}
.stage{min-height:300px;display:flex;flex-direction:column;align-items:center;justify-content:flex-start}
#mic{position:relative;width:132px;height:132px;border-radius:50%;border:0;cursor:pointer;
  background:radial-gradient(circle at 35% 30%,#6d8a6b,var(--sage-deep));
  box-shadow:0 10px 30px rgba(51,72,47,.28),inset 0 2px 6px rgba(255,255,255,.25);
  transition:transform .18s ease,box-shadow .18s ease;animation:breathe 4s ease-in-out infinite}
#mic:hover{transform:scale(1.05)}
#mic:active{transform:scale(.97)}
#mic svg{width:52px;height:52px;fill:#f6f4ec}
@keyframes breathe{0%,100%{box-shadow:0 10px 30px rgba(51,72,47,.28),0 0 0 0 rgba(76,107,79,.25)}
  50%{box-shadow:0 10px 30px rgba(51,72,47,.28),0 0 0 18px rgba(76,107,79,0)}}
#mic.rec{background:radial-gradient(circle at 35% 30%,#d4796b,#a03d31);animation:none}
#mic.rec::before,#mic.rec::after{content:'';position:absolute;inset:-6px;border-radius:50%;
  border:2px solid rgba(192,91,77,.5);animation:ring 1.6s ease-out infinite}
#mic.rec::after{animation-delay:.8s}
@keyframes ring{from{transform:scale(.92);opacity:1}to{transform:scale(1.35);opacity:0}}
#status{margin:1.1em 0 .2em;color:var(--muted);font-size:.95em;min-height:1.5em}
#timer{font-family:Georgia,serif;font-size:1.6em;color:var(--ink);min-height:1.4em}
#wave{display:none;margin-top:.6em}
.linklike{background:none;border:0;color:var(--muted);font-size:.85em;cursor:pointer;
  text-decoration:underline;text-underline-offset:3px;margin-top:1.6em}
.linklike:hover{color:var(--sage-deep)}
#typepanel{display:none;width:100%;margin-top:1em}
#typepanel.open{display:block;animation:fade .3s ease}
#typepanel textarea{width:100%;border:1px solid var(--line);border-radius:12px;background:var(--card);
  padding:.8em;font:inherit;resize:vertical}
.btn{background:var(--sage);color:#fff;border:0;border-radius:999px;padding:.65em 1.8em;
  font-size:1em;cursor:pointer;margin-top:.7em}
.btn:hover{background:var(--sage-deep)}
.card{width:100%;background:var(--card);border:1px solid var(--line);border-radius:16px;
  padding:1.2em 1.2em .8em;margin-top:1em;text-align:left;animation:fade .35s ease;
  box-shadow:0 6px 22px rgba(60,55,40,.07)}
@keyframes fade{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.heard{font-size:.85em;color:var(--muted);margin:0 0 .4em}
.follow{font-family:Georgia,serif;font-style:italic;font-size:1.15em;margin:.2em 0 .8em}
.cand{display:block;width:100%;text-align:left;background:transparent;border:1px solid var(--line);
  border-radius:12px;padding:.7em .9em;margin:.45em 0;cursor:pointer;font:inherit;color:inherit}
.cand:hover{border-color:var(--sage);background:#f3f1e6}
.cand .nm{font-weight:600}
.cand .id{color:var(--muted);font-weight:400;font-size:.85em}
.cand .bar{display:block;height:4px;border-radius:2px;background:var(--line);margin-top:.5em;overflow:hidden}
.cand .bar i{display:block;height:100%;background:var(--sage);border-radius:2px}
.cand .cf{float:right;color:var(--muted);font-size:.85em}
.ghost{background:none;border:0;color:var(--muted);font-size:.85em;cursor:pointer;
  text-decoration:underline;text-underline-offset:3px;display:block;margin:.7em auto .3em}
.violation{color:var(--rec);font-size:.85em}
.done{font-family:Georgia,serif;font-size:1.25em;margin:.4em 0}
.err{color:var(--rec);font-size:.9em;min-height:1.4em}
.spin{display:inline-block;width:22px;height:22px;border:3px solid var(--line);border-top-color:var(--sage);
  border-radius:50%;animation:spin 1s linear infinite;vertical-align:-5px}
@keyframes spin{to{transform:rotate(360deg)}}
footer{margin-top:auto;padding:1.6em;color:var(--muted);font-size:.8em;text-align:center}
#devline{font-size:.78em;color:var(--muted);margin:.2em 0 0;text-align:center}
@media (pointer:coarse){#mic{width:168px;height:168px}#mic svg{width:64px;height:64px}
main{padding-top:1.2em}.cand{padding:.95em 1em;font-size:1.05em}.btn{padding:.85em 2.1em}}
</style></head><body>
<main>
  <p class="brand">Fieldnotes</p>
  <p class="tag">speak &middot; identify &middot; log</p>
  <div class="pills" id="pills"></div>
  <div class="stage" id="stage">
    <button id="mic" aria-label="Speak"><svg viewBox="0 0 24 24"><path d="M12 15a3.5 3.5 0 0 0 3.5-3.5v-6a3.5 3.5 0 1 0-7 0v6A3.5 3.5 0 0 0 12 15zm6-3.5a6 6 0 0 1-12 0H4.5a7.5 7.5 0 0 0 6.5 7.44V21h2v-2.06a7.5 7.5 0 0 0 6.5-7.44H18z"/></svg></button>
    <div id="timer"></div>
    <canvas id="wave" width="220" height="40"></canvas>
    <div id="status">Tap the microphone and describe what you see</div>
    <div id="work"></div>
    <button class="linklike" id="typetoggle">or describe it in words &#9998;</button>
    <div id="typepanel">
      <textarea id="text" rows="3" placeholder="e.g. small brown bird with a black bib on a wire"></textarea><br>
      <button class="btn" onclick="fromText()">Identify</button>
    </div>
  </div>
  <p id="err" class="err"></p>
</main>
<div id="devline"></div>
<footer id="stats"></footer>
<script>
let REGION = 'gujarat', cur = null, rec = null, chunks = [], stream = null;
let actx = null, analyser = null, raf = null, secs = 0, tick = null;
const MAXS = 20;
async function api(path, body, raw) {
  const o = {};
  if (raw) { o.method = 'POST'; o.body = body; }
  else { o.headers = {'Content-Type': 'application/json'};
         if (body) { o.method = 'POST'; o.body = JSON.stringify(body); } }
  return (await fetch(path, o)).json();
}
async function load() {
  const r = await api('/api/regions');
  const avail = r.regions.length ? r.regions : ['gujarat'];
  if (!avail.includes(REGION)) REGION = avail[0];
  pills.innerHTML = avail.map(x =>
    `<button class="pill${x === REGION ? ' on' : ''}" onclick="setRegion('${x}')">${x}</button>`).join('');
  showStats(await api('/api/stats'));
}
function setRegion(x) { REGION = x; load(); }
function showStats(s) {
  stats.textContent = s.entries
    ? `${s.entries} entr${s.entries === 1 ? 'y' : 'ies'} · top-1 ${s.top1} · top-3 ${s.top3} · shortlist ${s.coverage}`
    : 'No entries yet — go outside and find something.';
}
function setStatus(t) { status.innerHTML = t; }
function drawWave() {
  const c = wave.getContext('2d'), W = wave.width, H = wave.height;
  const buf = new Uint8Array(analyser.frequencyBinCount);
  const paint = () => {
    raf = requestAnimationFrame(paint);
    analyser.getByteFrequencyData(buf);
    c.clearRect(0, 0, W, H);
    const n = 28, bw = W / n;
    for (let i = 0; i < n; i++) {
      const v = buf[Math.floor(i * buf.length / n)] / 255, h = 4 + v * (H - 8);
      c.fillStyle = '#4c6b4f';
      c.fillRect(i * bw + 1, (H - h) / 2, bw - 3, h);
    }
  };
  paint();
}
mic.onclick = async () => { rec ? stopRec(false) : startRec(); };
typetoggle.onclick = () => typepanel.classList.toggle('open');
async function startRec() {
  err.textContent = '';
  try {
    if (!stream) stream = await navigator.mediaDevices.getUserMedia({audio: true});
  } catch (e) { err.textContent = 'Microphone is blocked — allow it in the browser address bar.'; return; }
  chunks = [];
  const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';
  rec = mime ? new MediaRecorder(stream, {mimeType: mime}) : new MediaRecorder(stream);
  rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
  rec.onstop = finishRec;
  actx = actx || new (window.AudioContext || window.webkitAudioContext)();
  analyser = actx.createAnalyser();
  actx.createMediaStreamSource(stream).connect(analyser);
  rec.start();
  mic.classList.add('rec'); wave.style.display = 'block';
  drawWave();
  secs = 0; timer.textContent = '0:00';
  setStatus('Listening… tap to stop');
  tick = setInterval(() => {
    secs++;
    timer.textContent = '0:' + String(secs).padStart(2, '0');
    if (secs >= MAXS) stopRec(true);
  }, 1000);
}
function stopRec(auto) { if (rec && rec.state !== 'inactive') rec.stop(); }
async function finishRec() {
  clearInterval(tick); cancelAnimationFrame(raf);
  mic.classList.remove('rec'); wave.style.display = 'none'; timer.textContent = '';
  rec = null;
  const blob = new Blob(chunks, {type: rec && rec.mimeType ? rec.mimeType : 'audio/webm'});
  setStatus('<span class="spin"></span> Transcribing…');
  work.innerHTML = '';
  let t;
  try {
    t = await api('/api/transcribe', blob, true);
  } catch (e) { err.textContent = 'Could not reach the app — is it still running?'; setStatus('Tap the microphone and describe what you see'); return; }
  if (t.error) { err.textContent = t.error; setStatus('Tap the microphone and describe what you see'); return; }
  setStatus('Heard as: &ldquo;' + t.transcript.replace(/</g, '&lt;') + '&rdquo;');
  const d = await api('/api/identify', {text: t.transcript, region: REGION});
  if (d.error) { err.textContent = d.error; return; }
  cur = d;
  render(d);
}
async function fromText() {
  err.textContent = '';
  if (!text.value.trim()) { err.textContent = 'Write a word or two first.'; return; }
  setStatus('<span class="spin"></span> Thinking…');
  const d = await api('/api/identify', {text: text.value.trim(), region: REGION});
  if (d.error) { err.textContent = d.error; setStatus('Tap the microphone and describe what you see'); return; }
  cur = d;
  setStatus('From your notes');
  render(d);
}
function render(d) {
  work.innerHTML = `<div class="card"><p class="follow">${d.followup.replace(/</g, '&lt;')}</p>` +
    d.candidates.map(c =>
      `<button class="cand" onclick="pick('${c.id}')"><span class="cf">${c.confidence.toFixed(2)}</span>` +
      `<span class="nm">${c.common_name.replace(/</g, '&lt;')}</span> <span class="id">${c.id}</span>` +
      `<span class="bar"><i style="width:${Math.round(c.confidence * 100)}%"></i></span></button>`).join('') +
    `<button class="ghost" onclick="pick('none')">None of these — the right one isn't listed</button>` +
    (d.grounding_violation ? '<p class="violation">The model named something outside the shortlist; it was dropped.</p>' : '') +
    '</div>';
}
async function pick(id) {
  const d = await api('/api/confirm', Object.assign({}, cur, {confirmed_label: id, device: document.body.dataset.device, location: LOC}));
  if (d.error) { err.textContent = d.error; return; }
  work.innerHTML = `<div class="card" style="text-align:center"><p class="done">✓ Logged as ${id === 'none' ? 'unidentified' : id}</p>` +
    `<button class="ghost" onclick="again()">Identify another</button></div>`;
  setStatus('Nice spot. ' + (d.entry.confidence_source === 'rank' ? 'Confidence is rank-based.' : ''));
  showStats(d.stats);
}
function again() {
  work.innerHTML = ''; cur = null;
  setStatus('Tap the microphone and describe what you see');
}
const MOBILE = matchMedia('(pointer:coarse)').matches || /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent);
document.body.dataset.device = MOBILE ? 'mobile' : 'desktop';
let LOC = null;
function inGujarat() { return LOC && LOC.lat >= 20 && LOC.lat <= 24.8 && LOC.lon >= 68 && LOC.lon <= 74.6; }
function paintLoc() {
  let s = MOBILE ? 'mobile field mode' : 'laptop mode';
  s += LOC ? ' · ' + (inGujarat() ? 'Gujarat, India' : 'outside Gujarat') + ' · ±' + LOC.acc + ' m' : ' · location off';
  devline.textContent = s;
}
function locate() {
  if (!navigator.geolocation) { paintLoc(); return; }
  navigator.geolocation.getCurrentPosition(
    p => { LOC = {lat: +p.coords.latitude.toFixed(5), lon: +p.coords.longitude.toFixed(5), acc: Math.round(p.coords.accuracy || 0)}; paintLoc(); },
    () => paintLoc(), {timeout: 9000});
}
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
load();
locate();
</script></body></html>"""


def stats():
    try:
        with open(fn.JOURNAL, encoding="utf-8") as f:
            js = json.load(f)
    except (OSError, ValueError):
        js = []
    n = len(js)
    return {"entries": n,
            "top1": round(sum(1 for e in js if e.get("correct")) / n, 2) if n else 0,
            "top3": round(sum(1 for e in js if e.get("in_top3")) / n, 2) if n else 0,
            "coverage": round(sum(1 for e in js if e.get("in_shortlist")) / n, 2) if n else 0,
            "violations": sum(1 for e in js if e.get("model_answer", {}).get("grounding_violation"))}


def do_identify(data):
    text = (data.get("text") or "").strip()
    region = (data.get("region") or "gujarat").lower()
    if not text:
        return {"error": "Describe what you saw first."}
    try:
        short = fn.shortlist(text, fn.load_species(region))
    except SystemExit as e:
        return {"error": str(e)}
    try:
        ans, dt, src = fn.identify(text, short)
    except SystemExit as e:
        return {"error": str(e)}
    names = {s["id"]: s["common_name"] for s in short}
    cands = [{**c, "common_name": names.get(c["id"], "?")} for c in ans["candidates"]]
    return {"transcript": text, "region": region,
            "shortlist": [{"id": s["id"], "common_name": s["common_name"]} for s in short],
            "candidates": cands, "followup": ans["followup"],
            "grounding_violation": ans["grounding_violation"],
            "confidence_source": src, "latency_s": dt}


def do_transcribe(body, ctype):
    if not body:
        return {"error": "No audio arrived — try again."}
    ext = ".webm"
    for kind, suffix in (("wav", ".wav"), ("ogg", ".ogg"), ("mp4", ".m4a"), ("m4a", ".m4a")):
        if kind in (ctype or ""):
            ext = suffix
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {"error": "Voice needs the faster-whisper package installed."}
    fd, path = tempfile.mkstemp(suffix=ext, prefix="fieldnotes-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        segs, _ = WhisperModel("base.en", device="cpu", compute_type="int8").transcribe(path, beam_size=5)
        text = "".join(s.text for s in segs).strip()
    except Exception as e:
        return {"error": f"Could not transcribe that ({e})."}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if not text:
        return {"error": "Didn't catch that — come a little closer and try again."}
    return {"transcript": text}


def do_confirm(data):
    u = (data.get("confirmed_label") or "").strip()
    if not u:
        return {"error": "Pick the correct species or 'none'."}
    ids = data.get("shortlist", [])
    ids = [s["id"] if isinstance(s, dict) else s for s in ids]
    top3 = [c["id"] for c in data.get("candidates", [])]
    top = top3[0] if top3 else "none"
    entry = {"timestamp": datetime.datetime.now().astimezone().isoformat(),
             "transcript": data.get("transcript", ""), "region": data.get("region", ""),
             "shortlist": ids,
             "model_answer": {"candidates": data.get("candidates", []),
                              "followup": data.get("followup", ""),
                              "grounding_violation": bool(data.get("grounding_violation"))},
             "confirmed_label": u, "correct": bool(top3 and u == top),
             "in_top3": u in top3, "in_shortlist": u in ids,
             "device": data.get("device", "unknown"), "location": data.get("location"),
             "confidence_source": data.get("confidence_source", "model"),
             "latency_s": data.get("latency_s", 0)}
    n = fn.append_entry(entry)
    return {"saved": n, "entry": entry, "stats": stats()}


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(n)

    def do_GET(self):
        if self.path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/regions":
            self._json({"regions": fn.regions()})
        elif self.path == "/api/stats":
            self._json(stats())
        elif self.path == "/manifest.json":
            self._json(MANIFEST)
        elif self.path == "/sw.js":
            body = SW.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path in ("/icon-192.png", "/icon-512.png"):
            body = png_icon(192 if "192" in self.path else 512)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/api/transcribe":
            try:
                body = self._read()
            except (OSError, ValueError):
                return self._json({"error": "bad upload"}, 400)
            return self._json(do_transcribe(body, self.headers.get("Content-Type", "")))
        try:
            data = json.loads(self._read() or b"{}")
        except ValueError:
            return self._json({"error": "bad JSON"}, 400)
        if self.path == "/api/identify":
            return self._json(do_identify(data))
        if self.path == "/api/confirm":
            return self._json(do_confirm(data))
        return self._json({"error": "not found"}, 404)

    def log_message(self, *a):
        pass


def main():
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Timer(0.6, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    print(f"Fieldnotes UI at http://127.0.0.1:{PORT} (Ctrl+C to stop)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
