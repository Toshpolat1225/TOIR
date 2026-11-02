#!/usr/bin/env python3
"""TOIR <-> Wialon: FAQAT O'QISH. Natija terminalga chiqadi VA skript yonidagi matn faylga yoziladi
(wialon_natija_<buyruq>_<sana>.txt). Wialon'ga hech narsa yozilmaydi, TOIR DB'ga ulanilmaydi.

Buyruqlar:
  full [--unit 366] [--day 2026-10-30] [--reports 14,9]   HAMMASI BIR YO'LA + yakuniy xulosa (tavsiya etiladi)
  fleet [--list --cfl N]        barcha birliklar: cfl guruhlari, cnm/cneh anomaliyalari
  unit <id>                     bitta birlik: hisoblagich, sensorlar, parametrlar, sozlamalar
  history <id> --day YYYY-MM-DD xabarlar tarixi: odometr yig'indisi, GPS km, sakrashlar
  templates [--grep matn]       report shablonlari
  report <res> <tpl> <id> --day ... --run   hisobotni bajarish (faqat --run bilan)
Hamma buyruqda: --no-file  (faylga yozmaslik)

Token va sessiya ID hech qachon chop etilmaydi va faylga yozilmaydi.
"""
import argparse, json, math, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TZ = timezone(timedelta(hours=5))          # Toshkent
UNIT_FLAGS = 1 | 1024 | 4096 | 8192 | 131072 | 1048576 | 2097152
ERR = {1: "sessiya yaroqsiz", 2: "noto'g'ri svc", 4: "parametr noto'g'ri", 5: "ichki xato",
       6: "ruxsat/obyekt topilmadi", 7: "ruxsat yo'q", 8: "token/login xatosi", 10: "parallel limit",
       1001: "intervalda xabar yo'q", 1011: "IP o'zgargan/sessiya tugagan"}


class WialonError(Exception):
    def __init__(self, svc, code):
        desc = ERR.get(code, "noma'lum")
        super().__init__(f"{svc}: xato {code} ({desc})")
        self.code = code


# ---------------------------------------------------------------- transport
def load_env():
    import os
    env = {k: os.environ[k] for k in ("WIALON_HOST", "WIALON_TOKEN") if k in os.environ}
    for base in (Path(__file__).resolve().parent, Path.cwd()):
        p = base / ".env.local"
        if p.is_file():
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip("'\""))
            break
    return env


class Wialon:
    def __init__(self, host, token):
        self.host, self.token, self.sid = host.rstrip("/"), token, None

    def _raw(self, svc, params):
        form = {"svc": svc, "params": json.dumps(params, separators=(",", ":"))}
        if self.sid:
            form["sid"] = self.sid
        req = Request(self.host + "/wialon/ajax.html", urlencode(form).encode(),
                      {"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}") from None
        except (URLError, TimeoutError) as e:
            raise RuntimeError(f"ulanish xatosi: {type(getattr(e, 'reason', e)).__name__}") from None

    def call(self, svc, params):
        r = self._raw(svc, params)
        if isinstance(r, dict) and r.get("error"):
            raise WialonError(svc, r["error"])
        return r

    def login(self):
        r = self._raw("token/login", {"token": self.token})
        if not isinstance(r, dict) or not r.get("eid"):
            raise WialonError("token/login", r.get("error") if isinstance(r, dict) else "?")
        self.sid = r["eid"]
        return r

    def close(self):
        if self.sid:
            try:
                self._raw("core/logout", {})
            except Exception:
                pass
            self.sid = None


# ---------------------------------------------------------------- yordamchilar
def lt(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%Y-%m-%d %H:%M:%S") if ts else "yo'q"


def hms(sec):
    sec = int(round(sec))
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def decode_cfl(v):
    m = {0: "GPS", 1: "mileage sensor", 2: "relative odometer", 3: "GPS+ignition"}
    e = {0x00: "—", 0x10: "ignition sensor", 0x20: "absolute eng-hours sensor", 0x40: "relative eng-hours sensor"}
    x = [("mileage auto", 0x100), ("eng-hours auto", 0x200), ("GPRS auto", 0x400)]
    return (f"mileage={m.get(v & 0xF, '?')}; engine={e.get(v & 0xF0, '?')}; "
            + ", ".join(n for n, b in x if v & b))


def find_unit(w, uid, flags=UNIT_FLAGS):
    r = w.call("core/search_items", {"spec": {"itemsType": "avl_unit", "propName": "sys_id",
               "propValueMask": str(uid), "sortType": "sys_name", "propType": "property"},
               "force": 1, "flags": flags, "from": 0, "to": 0})
    if not r.get("items"):
        raise RuntimeError(f"birlik {uid} topilmadi")
    return r["items"][0]


def day_range(day):
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=TZ)
    return int(d.timestamp()), int(d.timestamp()) + 86399


def parse_local(s):
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(s, f).replace(tzinfo=TZ).timestamp())
        except ValueError:
            pass
    raise SystemExit(f"sana formati noto'g'ri: {s}")


def interval_from_args(a):
    if a.day:
        return day_range(a.day)
    if a.from_ and a.to:
        return parse_local(a.from_), parse_local(a.to)
    raise SystemExit("--day YYYY-MM-DD yoki --from va --to kerak (Toshkent vaqti)")


def haversine_m(y1, x1, y2, x2):
    p = math.pi / 180
    a = math.sin((y2 - y1) * p / 2) ** 2 + math.cos(y1 * p) * math.cos(y2 * p) * math.sin((x2 - x1) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------- fleet
def install_date(item):
    """'Дата установки' maxsus maydonidan (flds) sana; topilmasa None."""
    flds = item.get("flds")
    vals = flds.values() if isinstance(flds, dict) else (flds or [])
    for f in vals:
        n = str(f.get("n", "")).lower() if isinstance(f, dict) else ""
        if "дата" in n and "установ" in n:
            for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(str(f.get("v", "")).strip(), fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
    return None


def cmd_fleet(w, a):
    r = w.call("core/search_items", {"spec": {"itemsType": "avl_unit", "propName": "sys_name",
               "propValueMask": "*", "sortType": "sys_name", "propType": "property"},
               "force": 1, "flags": 1 | 8 | 1024 | 8192, "from": 0, "to": 0})
    items = r.get("items", [])
    now = datetime.now(timezone.utc).timestamp()
    print(f"Birliklar: {r.get('totalItemsCount')} (qaytdi {len(items)})  dataFlags={r.get('dataFlags')}")

    print("\n[cfl guruhlari]")
    g = {}
    for i in items:
        g.setdefault(i.get("cfl"), []).append(i)
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
        print(f"  cfl={k} (0x{int(k):X}): {len(v):>3} ta | {decode_cfl(int(k))}" if k is not None else f"  cfl yo'q: {len(v)}")

    print("\n[cnm (yurish hisoblagichi) taqsimoti]")
    for th in (1e5, 1e6, 1e7, 1e8, 1e9):
        print(f"  cnm >= {th:>13,.0f}: {sum((i.get('cnm') or 0) >= th for i in items)}")
    print("  Eng kattalari:")
    for i in sorted(items, key=lambda i: -(i.get("cnm") or 0))[:10]:
        print(f"   id={i['id']:<7} cfl={i.get('cfl')} cnm={i.get('cnm') or 0:>14,.0f}  cneh={i.get('cneh') or 0:>10,.1f}  {i['nm']}")

    print("\n[cneh (dvigatel-soati) eng kattalari]")
    for i in sorted(items, key=lambda i: -(i.get("cneh") or 0))[:8]:
        print(f"   id={i['id']:<7} cneh={i.get('cneh') or 0:>10,.1f}  {i['nm']}")

    print("\n[Ishonchlilik]  (ABSOLYUT qiymat emas, DELTA muhim: boshlang'ich qiymat o'rnatishda qo'lda kiritilgan bo'lishi mumkin)")
    strong, weak, zero_h = [], [], []
    nowdt = datetime.now(timezone.utc)
    no_date = 0
    for i in items:
        cn, ch = i.get("cnm") or 0, i.get("cneh") or 0
        v = cn / ch if ch > 1 else None
        inst = install_date(i)
        no_date += inst is None
        st, wk = [], []
        if v is not None and v > 100:
            st.append(f"o'rt.tezlik {v:,.0f} km/h")
        if ch / 8760 > 60:
            st.append(f"cneh {ch / 8760:,.0f} yil uzluksiz")
        elif ch / 8760 > 25:
            wk.append(f"cneh {ch / 8760:,.0f} yil uzluksiz")
        if cn > 1e6:
            st.append(f"cnm {cn:,.0f} > 1e6")
        if ch <= 1 and cn > 1000:
            zero_h.append(i)
        if inst and ch > (nowdt - inst).total_seconds() / 3600 and not st:
            wk.append(f"cneh o'rnatilgandan beri mumkin soatdan katta ({inst:%Y-%m-%d}) — boshlang'ich qiymat kiritilgan bo'lishi mumkin")
        if st:
            strong.append((i, st))
        elif wk:
            weak.append((i, wk))
    print(f"  A) ANIQ MUMKIN EMAS: {len(strong)} ta")
    for i, rs in sorted(strong, key=lambda x: -(x[0].get("cnm") or 0)):
        print(f"   id={i['id']:<7} cnm={i.get('cnm') or 0:>14,.0f} cneh={i.get('cneh') or 0:>12,.1f} {i['nm']}  -> {'; '.join(rs)}")
    print(f"  B) TEKSHIRISH KERAK: {len(weak)} ta")
    for i, rs in weak:
        print(f"   id={i['id']:<7} cnm={i.get('cnm') or 0:>14,.0f} cneh={i.get('cneh') or 0:>12,.1f} {i['nm']}  -> {'; '.join(rs)}")
    print(f"  C) cneh=0 lekin cnm>1000 (moto-soat HISOBLANMAYAPTI, 'ma'lumot yo'q' deb olinishi kerak): {len(zero_h)} ta")
    print("     misol:", ", ".join(f"{i['id']}:{i['nm']}" for i in zero_h[:6]), "..." if len(zero_h) > 6 else "")
    print(f"  O'rnatish sanasi topilmagan: {no_date} ta")

    if getattr(a, "list", False):
        print("\n[Faol birliklar ro'yxati] (oxirgi xabar < 2 kun)" + (f", cfl={a.cfl}" if getattr(a, "cfl", None) else ""))
        n = 0
        for i in items:
            t = (i.get("lmsg") or {}).get("t") or (i.get("pos") or {}).get("t")
            if not t or (now - t) / 86400 > 2 or (getattr(a, "cfl", None) and i.get("cfl") != a.cfl):
                continue
            n += 1
            if n <= 60:
                print(f"   id={i['id']:<7} cfl={i.get('cfl')} cnm={i.get('cnm') or 0:>12,.0f} cneh={i.get('cneh') or 0:>10,.1f}  {i['nm']}")
        print(f"   jami faol: {n}")

    print("\n[Xabar yangiligi]  (oxirgi xabar lmsg.t, bo'lmasa pos.t)")
    ages = []
    for i in items:
        t = (i.get("lmsg") or {}).get("t") or (i.get("pos") or {}).get("t")
        ages.append((now - t) / 86400 if t else None)
    print(f"  vaqti yo'q: {sum(x is None for x in ages)} | >7 kun: {sum(x is not None and x > 7 for x in ages)}"
          f" | >30 kun: {sum(x is not None and x > 30 for x in ages)}")
    return {"total": len(items), "strong": len(strong), "weak": len(weak), "zero_h": len(zero_h)}


# ---------------------------------------------------------------- unit
def junk_params(prms):
    out = {}
    for k, v in (prms or {}).items():
        x = v.get("v")
        if isinstance(x, (int, float)) and not isinstance(x, bool) and (abs(x) >= 1e12 or x == -2 ** 63):
            out.setdefault(datetime.fromtimestamp(v.get("ct", 0), timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), []).append(k)
    return out


def odo_scale(sensor):
    """Odometr sensori jadvalidan chiziqli koeffitsiyent: value = a*x + b (bitta qator bo'lsa)."""
    tbl = sensor.get("tbl") or []
    if len(tbl) == 1:
        return tbl[0].get("a", 1.0), tbl[0].get("b", 0.0)
    return 1.0, 0.0


def cmd_unit(w, a):
    it = find_unit(w, a.id)
    print(f"{it['nm']}  (id={it['id']})  mu={it.get('mu')}  netconn={it.get('netconn')}")
    print("\n[Hisoblagichlar]")
    print(f"  cnm={it.get('cnm')!r}  cneh={it.get('cneh')!r}  cnkb={it.get('cnkb')!r}")
    print(f"  cfl={it.get('cfl')} (0x{int(it.get('cfl', 0)):X}): {decode_cfl(int(it.get('cfl', 0)))}")
    pos, lm = it.get("pos") or {}, it.get("lmsg") or {}
    print(f"  pos.t={lt(pos.get('t'))}  lmsg.t={lt(lm.get('t'))}  tezlik={pos.get('s')}  sputnik={pos.get('sc')}")

    try:
        calc = w.call("unit/calc_last_message", {"unitId": a.id, "sensors": [], "flags": 1})
    except WialonError as e:
        calc = {}
        print("  calc_last_message:", e)
    prms = it.get("prms") or {}
    print("\n[Sensorlar]  id | nomi | turi | parametr/formula | hozirgi qiymat | manba-param yoshi")
    for s in (it.get("sens") or {}).values():
        p = s.get("p", "")
        pv = prms.get(p)
        src = ""
        if pv:
            src = f"param={pv.get('v')} o'zgargan={lt(pv.get('ct'))} oxirgi={lt(pv.get('at'))}"
        print(f"  {s['id']:>2} | {s['n']} | {s['t']} | {p} | {calc.get(str(s['id']), 'NA')} | {src}")
        if s.get("tbl"):
            print(f"       tbl={s['tbl']}")
        if s["t"] == "odometer":
            aa, bb = odo_scale(s)
            if it.get("cnm") and aa:
                print(f"       (taxminiy) cnm / a = {it['cnm'] / aa:,.0f} xom birlik — cnm shu sensordan to'plangan bo'lsa")

    print("\n[Shubhali parametrlar] (|qiymat|>=1e12 yoki -2^63), o'zgargan vaqti bo'yicha:")
    j = junk_params(prms)
    for t, ks in sorted(j.items()):
        print(f"  {t}: {len(ks)} ta  {', '.join(ks[:8])}{' ...' if len(ks) > 8 else ''}")
    if not j:
        print("  yo'q")

    for title, svc in (("report_settings", "unit/get_report_settings"), ("fuel_settings", "unit/get_fuel_settings"),
                       ("trip_detector", "unit/get_trip_detector")):
        try:
            print(f"\n[{title}]", json.dumps(w.call(svc, {"itemId": a.id}), ensure_ascii=False))
        except WialonError as e:
            print(f"\n[{title}]", e)
    return it


# ---------------------------------------------------------------- history
def analyze(msgs, odo_param, a_coef, b_coef, ign_param, max_gap=300, sample_n=0):
    """Sof funksiya. Odometr: Wialon 'relative odometer' modeli — qiymat kamaysa (reset), yangi qiymat qo'shiladi."""
    msgs = sorted((m for m in msgs if m.get("t")), key=lambda m: m["t"])
    res = {"n": len(msgs), "keys": {}, "gps_all_m": 0.0, "gps_ign_m": 0.0, "ign_s": 0.0, "moving_ign_s": 0.0,
           "gaps": 0, "ign_seen": 0, "odo_rel_km": 0.0, "odo_spike_km": 0.0, "odo_resets": 0, "spikes": [],
           "odo_min": None, "odo_max": None, "odo_pos_km": 0.0, "odo_sum_km": 0.0, "gps_fast_m": 0.0, "sample": []}
    prev_odo = prev_ign = prev_pos = prev_t = prev_speed = None
    for m in msgs:
        t, p = m["t"], m.get("p") or {}
        for k in p:
            res["keys"][k] = res["keys"].get(k, 0) + 1
        pos = m.get("pos")
        if prev_t is not None:
            dt = t - prev_t
            if dt > max_gap:
                res["gaps"] += 1
            if prev_ign == 1:
                res["ign_s"] += min(dt, max_gap)
                if (prev_speed or 0) >= 1:
                    res["moving_ign_s"] += min(dt, max_gap)
            if pos and "y" in pos and prev_pos:
                d = haversine_m(prev_pos["y"], prev_pos["x"], pos["y"], pos["x"])
                if d < 2000 and ((prev_speed or 0) >= 1 or pos.get("s", 0) >= 1) and pos.get("sc", 4) >= 4:
                    res["gps_all_m"] += d
                    if (prev_speed or 0) >= 5 and pos.get("s", 0) >= 5:
                        res["gps_fast_m"] += d
                    if prev_ign == 1:
                        res["gps_ign_m"] += d
        if pos and "y" in pos:
            prev_pos, prev_speed = pos, pos.get("s", 0)
        st = None
        if ign_param in p:
            st = 1 if p[ign_param] else 0
        elif ign_param[:2] == "in" and ign_param[2:].isdigit() and isinstance(p.get("in"), (int, float)):
            st = (int(p["in"]) >> (int(ign_param[2:]) - 1)) & 1      # in1 = 'in' bitmaskining 0-biti
        if st is not None:
            prev_ign = st
            res["ign_seen"] += 1
        v = p.get(odo_param)
        if isinstance(v, (int, float)):
            res["odo_min"] = v if res["odo_min"] is None else min(res["odo_min"], v)
            res["odo_max"] = v if res["odo_max"] is None else max(res["odo_max"], v)
            if prev_odo is not None:
                if v < prev_odo:
                    res["odo_resets"] += 1
                dv = v - prev_odo if v >= prev_odo else v
                km = dv * a_coef
                dt = (t - prev_t) if prev_t else 0
                if km > 2 + dt * 150 / 3600:
                    res["odo_spike_km"] += km
                    res["spikes"].append((t, prev_odo, v, km))
                else:
                    res["odo_rel_km"] += km
                    res["odo_pos_km"] += max(v - prev_odo, 0) * a_coef      # B: faqat musbat farqlar
                    res["odo_sum_km"] += v * a_coef                          # C: har xabardagi qiymat yig'indisi
                if sample_n and len(res["sample"]) < sample_n and (pos or {}).get("s", 0) >= 20:
                    res["sample"].append((t, (pos or {}).get("s"), v))
            prev_odo = v
        prev_t = t
    return res


def load_messages(w, uid, t0, t1, step=6 * 3600):
    out, t = [], t0
    while t <= t1:
        e = min(t + step - 1, t1)
        try:
            r = w.call("messages/load_interval", {"itemId": uid, "timeFrom": t, "timeTo": e,
                       "flags": 0, "flagsMask": 65280, "loadCount": 4294967295})
            out += r.get("messages", [])
        except WialonError as ex:
            if ex.code != 1001:      # 1001 = bu oraliqda xabar yo'q
                raise
        t = e + 1
    try:
        w.call("messages/unload", {})
    except Exception:
        pass
    return out


def cmd_history(w, a):
    t0, t1 = interval_from_args(a)
    it = find_unit(w, a.id, 1 | 4096 | 8192)
    sens = list((it.get("sens") or {}).values())
    odo = next((x for x in sens if x["t"] == "odometer"), None)
    ign = next((x for x in sens if x["t"] == "engine operation"), None)
    odo_param = a.odo or (odo and odo.get("p")) or "param199"
    ign_param = a.ign or (ign and ign.get("p")) or "in1"
    ac, bc = odo_scale(odo) if odo else (1.0, 0.0)
    print(f"{it['nm']} | {lt(t0)} — {lt(t1)} (GMT+5) | odometr param={odo_param} a={ac} | kontakt param={ign_param}")
    msgs = load_messages(w, a.id, t0, t1)
    r = analyze(msgs, odo_param, ac, bc, ign_param, sample_n=a.sample)
    top = sorted(r["keys"].items(), key=lambda kv: -kv[1])[:12]
    print(f"\nXabarlar: {r['n']} | 300 s dan uzun uzilishlar: {r['gaps']}")
    print("  Xabarlardagi parametrlar (soni):", ", ".join(f"{k}={v}" for k, v in top))
    print(f"  ODOMETR yig'indisi (relative = qiymatlar yig'indisi, cnm manbai): {r['odo_sum_km']:9.2f} km")
    print(f"  GPS masofa, tezlik>=5 (titrashsiz):                              {r['gps_fast_m'] / 1000:9.2f} km")
    print(f"  GPS masofa, barcha harakatli bo'laklar (titrash bilan):          {r['gps_all_m'] / 1000:9.2f} km")
    if r["ign_seen"]:
        print(f"  Kontakt yoqiq vaqt: {hms(r['ign_s'])} | shundan tezlik>=1: {hms(r['moving_ign_s'])}")
    else:
        print(f"  Kontakt ({ign_param}) xabarlarda yo'q — moto-soatni xabarlardan emas, report yoki cneh o'sishidan oling.")
    print(f"  Odometr sakrashlari (>2 km/xabar): {r['odo_spike_km']:,.2f} km ({len(r['spikes'])} ta) | xom min/max: {r['odo_min']} / {r['odo_max']}")
    for t, p0, p1, km in r["spikes"][:15]:
        print(f"    SAKRASH {lt(t)}: {p0} -> {p1}  (+{km:,.1f} km)")
    if r["sample"]:
        print(f"\n  NAMUNA (harakatdagi {len(r['sample'])} xabar): vaqt | tezlik km/h | {odo_param} xom")
        for t, sp, v in r["sample"]:
            print(f"    {lt(t)[11:]} | {sp:>3} | {v}")
    if getattr(a, "cnm0", None) is not None and getattr(a, "cnm1", None) is not None:
        print(f"\n  TAQQOSLASH: Wialon cnm o'sishi = {a.cnm1 - a.cnm0:,.0f} km (butun km, +-1) | "
              f"odometr yig'indisi = {r['odo_sum_km']:.1f} | GPS(tezlik>=5) = {r['gps_fast_m'] / 1000:.1f} km")
    return r


# ---------------------------------------------------------------- templates / report
def cmd_templates(w, a):
    r = w.call("core/search_items", {"spec": {"itemsType": "avl_resource", "propName": "sys_name",
               "propValueMask": "*", "sortType": "sys_name", "propType": "property"},
               "force": 1, "flags": 1 | 8192, "from": 0, "to": 0})
    n = 0
    for res in r.get("items", []):
        for t in (res.get("rep") or {}).values():
            name = t.get("n", "")
            if a.grep and a.grep.lower() not in name.lower():
                continue
            n += 1
            print(f"res={res['id']} ({res['nm']}) tpl={t['id']} | {name} | {t.get('ct')}")
            if a.grep:      # tafsilot faqat filtr bilan
                for fl in (4, 0):
                    try:
                        d = w.call("report/get_report_data", {"itemId": res["id"], "col": [t["id"]], "flags": fl})
                        tpl = d[0] if isinstance(d, list) and d else d
                        for tb in (tpl.get("tbl") or []):
                            print(f"    jadval {tb.get('n')} | {tb.get('l')}\n      ustunlar: {tb.get('cl')}")
                        break
                    except WialonError as e:
                        print(f"    get_report_data flags={fl}: {e}")
    print(f"\nJami ko'rsatildi: {n}")


def cell(c):
    return str(c.get("t", c.get("v", ""))) if isinstance(c, dict) else str(c)


def cmd_report(w, a):
    if not a.run:
        raise SystemExit("Hisobot bajarish uchun --run qo'shing (sessiyada vaqtinchalik natija yaratadi, hech narsa o'zgartirmaydi).")
    t0, t1 = interval_from_args(a)
    print(f"Hisobot res={a.res} tpl={a.tpl} unit={a.id} | {lt(t0)} — {lt(t1)} (GMT+5; UNIX {t0}..{t1})")
    try:
        w.call("report/cleanup_result", {})
    except WialonError:
        pass
    stats = {}
    try:
        r = w.call("report/exec_report", {"reportResourceId": a.res, "reportTemplateId": a.tpl,
                   "reportObjectId": a.id, "reportObjectSecId": 0,
                   "interval": {"from": t0, "to": t1, "flags": 0}})
        rr = r.get("reportResult", {})
        if not rr.get("stats") and not rr.get("tables"):
            print("  BO'SH natija. Javob kalitlari:", list(r.keys()), "| reportResult:", {k: (v if not isinstance(v, (list, dict)) else f"{type(v).__name__}[{len(v)}]") for k, v in rr.items()})
        print("\n[Statistika]  (Eslatma: API hisobot vaqtlari UTC'da bo'lishi mumkin — 'Начало интервала' ga qarang)")
        for row in rr.get("stats", []):
            print("  ", " : ".join(map(str, row)))
            if len(row) >= 2:
                stats[str(row[0])] = row[1]
        for i, tb in enumerate(rr.get("tables", [])):
            rows = tb.get("rows", 0)
            print(f"\n[Jadval {i}] {tb.get('name')} | {tb.get('label')} | qatorlar={rows}")
            print("  ustunlar:", tb.get("header"))
            if rows and a.rows:
                data = w.call("report/select_result_rows", {"tableIndex": i, "config": {
                    "type": "range", "data": {"from": 0, "to": min(rows, a.rows) - 1, "level": 0, "unitInfo": 1}}})
                for row in data:
                    print("   ", " | ".join(cell(c) for c in row.get("c", [])))
                if rows > a.rows:
                    print(f"    ... yana {rows - a.rows} qator ko'rsatilmadi (--rows {rows})")
    finally:
        try:
            w.call("report/cleanup_result", {})
        except Exception:
            pass
    return stats


# ---------------------------------------------------------------- full
def num(x):
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(x))
    return float(m.group().replace(",", ".")) if m else None


def section(title):
    print("\n" + "=" * 100 + f"\n{title}\n" + "=" * 100)


def attempt(fn, *args):
    try:
        return fn(*args)
    except (WialonError, RuntimeError) as e:
        print("  XATO:", e)
        return None


def cmd_full(w, a):
    if not a.day:
        a.day = (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    ns = argparse.Namespace
    section(f"1/6  FLOTA (barcha birliklar)")
    fl = attempt(cmd_fleet, w, ns(list=False, cfl=None))
    section(f"2/6  BIRLIK {a.unit}: hisoblagich, sensorlar, sozlamalar")
    it = attempt(cmd_unit, w, ns(id=a.unit))
    section(f"3/6  XABARLAR TARIXI {a.day} (birlik {a.unit})")
    hr = attempt(cmd_history, w, ns(id=a.unit, day=a.day, from_=None, to=None, odo=None, ign=None,
                                    sample=0, cnm0=None, cnm1=None))
    section("4/6  REPORT SHABLONLARI")
    attempt(cmd_templates, w, ns(grep=None))
    reps = {}
    for tpl in [int(x) for x in a.reports.split(",") if x.strip()]:
        section(f"5/6  HISOBOT: shablon {tpl}, birlik {a.unit}, {a.day}")
        reps[tpl] = attempt(cmd_report, w, ns(res=a.res, tpl=tpl, id=a.unit, run=True, rows=0,
                                              day=a.day, from_=None, to=None)) or {}

    section("6/6  XULOSA (avtomatik)")
    if fl:
        print(f"  [FLOTA] jami {fl['total']} ta. Aniq mumkin emas: {fl['strong']}, tekshirish kerak: {fl['weak']}, "
              f"cneh=0 (ma'lumot yo'q): {fl['zero_h']}")
    if it:
        cn, ch = it.get("cnm") or 0, it.get("cneh") or 0
        if cn > 1e6 or (ch > 1 and cn / ch > 100):
            print(f"  [DIQQAT] {it['nm']}: cnm={cn:,.0f} — absolyut qiymatga ishonmang, TOIR'ga baseline + delta bilan oling.")
        else:
            print(f"  [OK] {it['nm']}: cnm={cn:,.0f}, cneh={ch:,.1f} — mantiqiy ko'rinadi.")
        if ch <= 1 and cn > 1000:
            print("  [MA'LUMOT YO'Q] cneh=0 — bu '0 soat' emas, moto-soat hisoblanmayapti.")
        junk = junk_params(it.get("prms"))
        if junk:
            print(f"  [DIQQAT] buzilgan parametrlar bor: {', '.join(f'{k} ({len(v)} ta)' for k, v in sorted(junk.items()))}")
    if hr:
        if hr["spikes"]:
            print(f"  [DIQQAT] {a.day}: odometrda {len(hr['spikes'])} ta sakrash — hisoblagich shu kuni buzilgan.")
        else:
            print(f"  [OK] {a.day}: odometrda sakrash yo'q.")
        rep = None
        for tpl, st in reps.items():
            for k, v in st.items():
                if "Пробег по GPS" in k or "Пробег в поездках" in k:
                    if num(v) is not None:
                        rep = (tpl, k, num(v)); break
            if rep:
                break
        if rep and rep[2] > 0:
            diff = (hr["odo_sum_km"] - rep[2]) / rep[2] * 100
            tag = "OK" if abs(diff) <= 3 else ("YAQIN" if abs(diff) <= 10 else "FARQ KATTA")
            print(f"  [{tag}] odometr yig'indisi {hr['odo_sum_km']:.2f} km vs report (shablon {rep[0]}, '{rep[1]}') {rep[2]:.2f} km: farq {diff:+.1f}%")
        elif reps:
            print("  [NOMA'LUM] reportdan masofa o'qilmadi (stats'da 'Пробег по GPS' / 'Пробег в поездках' yo'q).")
    for tpl, st in reps.items():
        for k, v in st.items():
            if "Машиночасы" in k or "Моточасы" in k:
                print(f"  [MOTO-SOAT] shablon {tpl}: {k} = {v}")
    print("  [ESLATMA] API report vaqtlari UTC'da (Toshkent = UTC+5).")


# ---------------------------------------------------------------- tee (terminal + fayl)
class Tee:
    def __init__(self, stream, fh, secrets):
        self.stream, self.fh, self.secrets = stream, fh, secrets

    def write(self, s):
        for sec in self.secrets():
            if sec:
                s = s.replace(sec, "***")
        self.stream.write(s)
        if self.fh:
            self.fh.write(s)
        return len(s)

    def flush(self):
        self.stream.flush()
        if self.fh:
            self.fh.flush()


def open_log(cmd):
    name = f"wialon_natija_{cmd}_{datetime.now(TZ):%Y%m%d_%H%M%S}.txt"
    for base in (Path(__file__).resolve().parent, Path.cwd()):
        try:
            p = base / name
            return open(p, "w", encoding="utf-8-sig"), p
        except OSError:
            continue
    return None, None


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-file", action="store_true", help="natijani faylga yozmaslik")
    sp = ap.add_subparsers(dest="cmd", required=True)
    fu = sp.add_parser("full", parents=[common])
    fu.add_argument("--unit", type=int, default=366); fu.add_argument("--day")
    fu.add_argument("--res", type=int, default=88); fu.add_argument("--reports", default="14,9")
    f = sp.add_parser("fleet", parents=[common]); f.add_argument("--list", action="store_true"); f.add_argument("--cfl", type=int)
    u = sp.add_parser("unit", parents=[common]); u.add_argument("id", type=int)
    h = sp.add_parser("history", parents=[common]); h.add_argument("id", type=int)
    t = sp.add_parser("templates", parents=[common]); t.add_argument("--grep")
    r = sp.add_parser("report", parents=[common])
    r.add_argument("res", type=int); r.add_argument("tpl", type=int); r.add_argument("id", type=int)
    r.add_argument("--run", action="store_true"); r.add_argument("--rows", type=int, default=40)
    for p in (h, r):
        p.add_argument("--day"); p.add_argument("--from", dest="from_"); p.add_argument("--to")
    h.add_argument("--odo"); h.add_argument("--ign")
    h.add_argument("--sample", type=int, default=0); h.add_argument("--cnm0", type=float); h.add_argument("--cnm1", type=float)
    a = ap.parse_args()

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    env = load_env()
    if not env.get("WIALON_HOST", "").startswith("https://") or not env.get("WIALON_TOKEN"):
        print("CONFIG XATOSI: WIALON_HOST (https://...) va WIALON_TOKEN kerak (.env.local yoki muhit)."); return 1
    w = Wialon(env["WIALON_HOST"], env["WIALON_TOKEN"])
    fh, path = (None, None) if a.no_file else open_log(a.cmd)
    real = sys.stdout
    sys.stdout = Tee(real, fh, lambda: (w.token, w.sid))
    code = 0
    try:
        print(f"Sana: {datetime.now(TZ):%Y-%m-%d %H:%M:%S} (Toshkent) | buyruq: {' '.join(sys.argv[1:])}")
        w.login()
        print("LOGIN OK\n")
        {"full": cmd_full, "fleet": cmd_fleet, "unit": cmd_unit, "history": cmd_history,
         "templates": cmd_templates, "report": cmd_report}[a.cmd](w, a)
        print("\nTUGADI. Wialon'ga hech narsa yozilmadi, TOIR DB'ga ulanilmadi.")
    except (WialonError, RuntimeError) as e:
        print("XATO:", e); code = 1
    finally:
        w.close()
        sys.stdout = real
        if fh:
            fh.close()
            print(f"\nNatija fayli: {path}")
        elif not a.no_file:
            print("\nOGOHLANTIRISH: natija fayli yaratilmadi (papkaga yozish mumkin emas).")
    return code


if __name__ == "__main__":
    sys.exit(main())