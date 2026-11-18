"""Live voice pipeline check: each sample wav -> /assistant/transcribe -> /assistant/command, compared with what the SAME command says when the
expected text is typed. Reports transcript, intent agreement and the latency of every stage. Read-only. Needs zz_lib.py's files next to it.

Samples: speech_samples/ (Windows Russian voice; add your own recordings: <id>.wav + an entry {id, expect} in phrases.json, then run with --language uz).
"""
import json
import os
import sys
import time

import httpx

from zz_lib import CREDS, rec

HOST = os.environ.get("TOIR_HOST", "192.168.28.104")
ROOT_CERT = os.environ.get("TOIR_ROOT_CERT", "toir-local-root.crt")
API = f"https://{HOST}/api/v1"
AREA = "voice-pipeline"
HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.environ.get("SPEECH_SAMPLES", os.path.join(HERE, "speech_samples"))
LANGUAGE = sys.argv[sys.argv.index("--language") + 1] if "--language" in sys.argv else "ru"

c = httpx.Client(base_url=API, timeout=120, verify=ROOT_CERT)
token = c.post("/auth/login", json={"email": CREDS["admin"]["email"], "password": CREDS["admin"]["password"]}).json()["access_token"]
h = {"Authorization": f"Bearer {token}"}
st = c.get("/assistant/status", headers=h).json()
rec(AREA, "voice service is available", "PASS" if st.get("voice_available") else "FAIL", str(st), "high")
phrases = json.load(open(os.path.join(SAMPLES, "phrases.json"), encoding="utf-8"))
agree = 0
for p in phrases:
    wav = os.path.join(SAMPLES, f"{p['id']}.wav")
    if not os.path.exists(wav):
        continue
    t0 = time.perf_counter()
    r = c.post("/assistant/transcribe", files={"audio": (f"{p['id']}.wav", open(wav, "rb").read(), "audio/wav")}, data={"language": LANGUAGE}, headers=h)
    t_stt = time.perf_counter() - t0
    if r.status_code != 200:
        rec(AREA, f"{p['id']}: transcribe", "FAIL", f"{r.status_code} {r.text[:100]}", "high")
        continue
    heard = r.json()
    t1 = time.perf_counter()
    spoken = c.post("/assistant/command", json={"text": heard["text"], "source": "voice", "stt_confidence": heard.get("confidence")}, headers=h).json()
    typed = c.post("/assistant/command", json={"text": p["expect"]}, headers=h).json()
    same = spoken.get("intent") == typed.get("intent") and spoken.get("intent") is not None
    agree += 1 if same else 0
    rec(AREA, f"{p['id']}: «{heard['text']}» -> {spoken.get('intent')} (typed: {typed.get('intent')}) stt {t_stt:.1f}s cmd {(time.perf_counter() - t1) * 1000:.0f}ms", "PASS" if same else "FAIL", f"expected text: {p['expect']}", "medium")
n = sum(1 for p in phrases if os.path.exists(os.path.join(SAMPLES, f"{p['id']}.wav")))
rec(AREA, f"intent agreement over the voice samples: {agree}/{n}", "PASS" if n and agree >= 0.8 * n else "FAIL", f"language={LANGUAGE}", "high")
print(f"done: voice pipeline {agree}/{n}")
