"""Measures the local speech recogniser: text accuracy (WER after normalising numbers), number exactness and latency per clip.

Usage:  python speech_measure.py --url http://127.0.0.1:19000 [--language ru|uz|auto] [--no-prompt] [--repeat 2] [--samples speech_samples]
Samples: speech_samples/phrases.json (id, say, expect) + <id>.wav. To measure Uzbek, record your own phrases the same way (see the end of this file).
"""
import argparse
import json
import re
import statistics
import time
from pathlib import Path

import httpx

DOMAIN_PROMPT = (
    "Buyruqlar: naryad, naryadlar, sostav, lokomotiv, vagon, teplovoz, elektrovoz, Wialon, GTK, vesovoy, tarozi, texnik xizmat, ТО, probeg, "
    "xarita, qayerda, nechta, bugun, kecha. Команды: наряд, состав, локомотив, вагон, Виалон, ГТК, весовая, ТО, пробег, карта, где, сколько, "
    "сегодня, вчера. Номера: тридцать семь девятьсот девятнадцать, 37919, o'ttiz yetti to'qqiz yuz o'n to'qqiz."
)

UNITS = {"ноль": 0, "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
         "десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16,
         "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19}
TENS = {"двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90}
HUNDREDS = {"сто": 100, "двести": 200, "триста": 300, "четыреста": 400, "пятьсот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800, "девятьсот": 900}
THOUSAND = {"тысяча", "тысячи", "тысяч"}


def numbers_from_words(tokens: list[str]) -> list[str]:
    """Replace runs of Russian number words by the digits they denote (so «тридцать семь тысяч девятьсот девятнадцать» == 37919)."""
    out, i = [], 0
    while i < len(tokens):
        if tokens[i] in UNITS or tokens[i] in TENS or tokens[i] in HUNDREDS or tokens[i] in THOUSAND:
            total, current, j = 0, 0, i
            while j < len(tokens) and (tokens[j] in UNITS or tokens[j] in TENS or tokens[j] in HUNDREDS or tokens[j] in THOUSAND):
                t = tokens[j]
                if t in THOUSAND:
                    total += (current or 1) * 1000
                    current = 0
                else:
                    current += UNITS.get(t) or TENS.get(t) or HUNDREDS.get(t) or 0
                j += 1
            out.append(str(total + current))
            i = j
        else:
            out.append(tokens[i])
            i += 1
    return out


def normalise(text: str) -> list[str]:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    tokens = numbers_from_words([t.replace("ё", "е") for t in tokens])
    # the recogniser may split 37919 into "37 919": glue digit groups
    glued, buf = [], ""
    for t in tokens:
        if t.isdigit():
            buf += t
        else:
            if buf:
                glued.append(buf)
                buf = ""
            glued.append(t)
    if buf:
        glued.append(buf)
    return glued


def wer(reference: list[str], hypothesis: list[str]) -> float:
    d = [[0] * (len(hypothesis) + 1) for _ in range(len(reference) + 1)]
    for i in range(len(reference) + 1):
        d[i][0] = i
    for j in range(len(hypothesis) + 1):
        d[0][j] = j
    for i in range(1, len(reference) + 1):
        for j in range(1, len(hypothesis) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (reference[i - 1] != hypothesis[j - 1]))
    return d[-1][-1] / max(1, len(reference))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:19000")
    ap.add_argument("--samples", default=str(Path(__file__).parent / "speech_samples"))
    ap.add_argument("--language", default="ru")
    ap.add_argument("--no-prompt", action="store_true")
    ap.add_argument("--repeat", type=int, default=2, help="runs per clip (the first run warms the model up and is reported apart)")
    args = ap.parse_args()
    samples = json.loads((Path(args.samples) / "phrases.json").read_text(encoding="utf-8"))
    client = httpx.Client(timeout=120)
    health = client.get(f"{args.url}/health").json()
    rows, first_ms, later_ms, wers, num_ok, num_total = [], [], [], [], 0, 0
    for run in range(args.repeat):
        for s in samples:
            wav = (Path(args.samples) / f"{s['id']}.wav").read_bytes()
            data = {"language": args.language}
            if not args.no_prompt:
                data["prompt"] = DOMAIN_PROMPT
            t0 = time.perf_counter()
            r = client.post(f"{args.url}/transcribe", data=data, files={"audio": (f"{s['id']}.wav", wav, "audio/wav")})
            wall = (time.perf_counter() - t0) * 1000
            if r.status_code != 200:
                rows.append((s["id"], run, r.status_code, r.text[:60], 0, 0, 0))
                continue
            body = r.json()
            ref, hyp = normalise(s["expect"]), normalise(body["text"])
            w = wer(ref, hyp)
            nums_ref = [t for t in ref if t.isdigit()]
            nums_hyp = [t for t in hyp if t.isdigit()]
            if run == args.repeat - 1:
                wers.append(w)
                num_total += len(nums_ref)
                num_ok += sum(1 for t in nums_ref if t in nums_hyp)
            (first_ms if run == 0 else later_ms).append(body["ms"])
            rows.append((s["id"], run, 200, body["text"], round(w, 2), body["ms"], round(body["duration_s"], 1)))
    print(f"model={health.get('model')} language={args.language} prompt={'no' if args.no_prompt else 'yes'}")
    for row in rows:
        if row[1] == args.repeat - 1:
            print(f"{row[0]}  wer={row[4]:<4} {row[5]:>5} ms  audio={row[6]}s  ->  {row[3]}")
    summary = {
        "model": health.get("model"), "language": args.language, "prompt": not args.no_prompt, "clips": len(samples),
        "wer_mean": round(statistics.mean(wers), 3) if wers else None, "phrases_exact": sum(1 for w in wers if w == 0), "numbers_exact": f"{num_ok}/{num_total}",
        "ms_first_run_mean": round(statistics.mean(first_ms)) if first_ms else None,
        "ms_warm_mean": round(statistics.mean(later_ms)) if later_ms else None, "ms_warm_max": max(later_ms) if later_ms else None,
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

# Measuring Uzbek: record 10 phrases on a phone (WAV/M4A/WebM is fine), e.g. "37919 qayerda", "naryadlar nechta", "bugun necha km yurdi",
# "ottiz yetti to'qqiz yuz o'n to'qqiz ni top", "439 sostavda nechta vagon bor", "muddati o'tgan texnik xizmatlar", "yordam", "xaritani och",
# "vesovoyda bugun necha tonna", "oxirgi audit hodisalari". Put the files and a phrases.json (id, expect; the wavs are named <id>.wav) into a folder and run with
# --samples <folder> --language uz (and once with --language auto). The WER here is computed on the normalised words, digits as digits.
