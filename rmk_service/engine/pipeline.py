"""Pełny przebieg: PDF -> wykrycie wystawcy -> parser -> podział RMK -> nakładka."""
import os, json, functools
from decimal import Decimal
from detect import detect_vendor
from parsers import PARSERS, parse_orange, parse_tmobile
from plus_parser import parse_plus
from rmk_core import split_rmk, q2, ROMAN
from stamp import stamp, pln

_CFG = json.load(open(os.path.join(os.path.dirname(__file__), "config.json")))

ALL_PARSERS = dict(PARSERS)
ALL_PARSERS["Plus (Polkomtel)"] = parse_plus
ALL_PARSERS["Orange"] = functools.partial(parse_orange, excluded=_CFG["orange_numery_wylaczone"])
ALL_PARSERS["T-Mobile"] = parse_tmobile

SUPPORTED = set(ALL_PARSERS)

def _dm(d):
    return d.strftime("%d.%m")

def _compute_tmobile(p):
    """Dzielimy pozycje bieżącego okresu. Pozycje poprzedniego okresu (korzystanie/z dołu) → w całości do 1. miesiąca."""
    r = split_rmk(p["netto"], p["okres_od"], p["okres_do"])
    rows = {row["mies"]: q2(row["kwota"]) for row in r["rows"]}
    first_m = r["rows"][0]["mies"]
    dodatek = q2(p["poprzedni_okres"])
    if dodatek != 0:
        rows[first_m] = rows.get(first_m, Decimal("0.00")) + dodatek
    # linie nakładki
    n = pln(p["netto"]); td = r["total_days"]
    lines = [("RMK:", True)]
    kor = q2(p["korzystanie"])
    if kor != 0 and p.get("kor_okres"):
        lines.append((f"za korzystanie ({_dm(p['kor_okres'][0])}–{_dm(p['kor_okres'][1])}) = {pln(p['korzystanie'])} zł → {ROMAN[first_m]}", False))
    reszta = dodatek - kor
    if reszta != 0:
        lines.append((f"z poprz. okresu = {pln(reszta)} zł → {ROMAN[first_m]}", False))
    lines.append((f"{_dm(p['okres_od'])}–{_dm(p['okres_do'])} = {n} zł (abonament)", False))
    for row in r["rows"]:
        lines.append((f"{row['roman']}: {n} : {td} × {row['dni']} = {pln(row['kwota'])} zł", False))
    if dodatek != 0:
        base_first = q2(r["rows"][0]["kwota"])
        lines.append((f"{ROMAN[first_m]}: {pln(base_first)} + {pln(dodatek)} = {pln(rows[first_m])} zł", False))
    lines.append((f"razem: {pln(sum(rows.values()))} zł", True))
    p["overlay_lines"] = lines
    r["rows"] = [{"mies": m, "roman": ROMAN[m], "kwota": v, "dni": None} for m, v in sorted(rows.items())]
    target = round(float(q2(p["netto"]) + dodatek), 2)
    return r, float(sum(rows.values())), target

def _compute_orange(p):
    """Podział bazy + doliczenie numerów wyłączonych do miesiąca daty wystawienia + wierne linie."""
    r = split_rmk(p["netto"], p["okres_od"], p["okres_do"])
    wm = p["data_wystawienia"].month
    excl = q2(p["excl_sum"])
    rows = {row["mies"]: q2(row["kwota"]) for row in r["rows"]}
    if excl != 0:
        rows[wm] = rows.get(wm, Decimal("0.00")) + excl
    # linie nakładki (wiernie jak odręczny wzór)
    n_base = pln(p["netto"]); td = r["total_days"]; tot = pln(p["netto_total"])
    lines = [("RMK:", True)]
    if excl != 0:
        nums = ", ".join(w["numer"] for w in p["wylaczone"])
        lines.append((f"{tot} − {pln(p['excl_sum'])} (nr {nums}) = {n_base} zł", False))
    for row in r["rows"]:
        lines.append((f"{row['roman']}: {n_base} : {td} × {row['dni']} = {pln(row['kwota'])} zł", False))
    if excl != 0:
        base_wm = q2(next((row["kwota"] for row in r["rows"] if row["mies"] == wm), Decimal("0")))
        lines.append((f"{ROMAN[wm]}: {pln(base_wm)} + {pln(p['excl_sum'])} = {pln(rows[wm])} zł", False))
    lines.append((f"razem: {pln(sum(rows.values()))} zł", True))
    p["overlay_lines"] = lines
    r["rows"] = [{"mies": m, "roman": ROMAN[m], "kwota": v, "dni": None} for m, v in sorted(rows.items())]
    return r, float(sum(rows.values())), p["netto_total"]

def _dm(d):
    return d.strftime("%d.%m")

def _compute_plus(p):
    """Dzieli KAŻDY okres osobno i sumuje po miesiącach. Nakładka pokazuje rozbicie na okresy."""
    monthly = {}
    blocks = []
    for per in p["periods"]:
        rr = split_rmk(per["netto"], per["od"], per["do"])
        alloc = []
        for row in rr["rows"]:
            monthly[row["mies"]] = monthly.get(row["mies"], Decimal("0.00")) + q2(row["kwota"])
            alloc.append((row["roman"], q2(row["kwota"]), row["dni"], rr["total_days"]))
        blocks.append((per, alloc))
    lines = [("RMK:", True)]
    if len(p["periods"]) == 1:
        per, alloc = blocks[0]
        n = pln(per["netto"]); td = alloc[0][3]
        for roman, kw, dni, _ in alloc:
            lines.append((f"{roman}: {n} : {td} × {dni} = {pln(kw)} zł", False))
    else:
        for per, alloc in blocks:
            npln = pln(per["netto"])
            lines.append((f"{_dm(per['od'])}–{_dm(per['do'])} = {npln} zł:", False))
            for roman, kw, dni, td in alloc:
                if len(alloc) == 1:
                    lines.append((f"   {roman}: {pln(kw)} zł (cały)", False))
                else:
                    lines.append((f"   {roman}: {npln} : {td} × {dni} = {pln(kw)} zł", False))
        podsum = "   ".join(f"{ROMAN[m]}: {pln(v)}" for m, v in sorted(monthly.items()))
        lines.append((f"Σ  {podsum}", False))
    lines.append((f"razem: {pln(sum(monthly.values()))} zł", True))
    p["overlay_lines"] = lines
    r = {"rows": [{"mies": m, "roman": ROMAN[m], "kwota": v, "dni": None} for m, v in sorted(monthly.items())],
         "total_days": None, "netto": q2(p["netto"])}
    return r, float(sum(monthly.values())), p["netto"]

def process(in_path, out_dir, mode="auto"):
    vendor = detect_vendor(in_path)
    if vendor not in ALL_PARSERS:
        return {"ok": False, "vendor": vendor, "reason": "parser jeszcze nie gotowy"}
    p = ALL_PARSERS[vendor](in_path)
    if vendor == "Plus (Polkomtel)":
        r, suma, check_target = _compute_plus(p)
    elif vendor == "Orange":
        r, suma, check_target = _compute_orange(p)
    elif vendor == "T-Mobile":
        r, suma, check_target = _compute_tmobile(p)
    else:
        r = split_rmk(p["netto"], p["okres_od"], p["okres_do"])
        suma = float(sum(x["kwota"] for x in r["rows"]))
        check_target = p["netto"]
    base = os.path.splitext(os.path.basename(in_path))[0]
    out_path = os.path.join(out_dir, f"{base}_wyliczone.pdf")
    os.makedirs(out_dir, exist_ok=True)
    placed = stamp(in_path, out_path, p, r, mode=mode)
    return {"ok": True, "vendor": vendor, "parsed": p, "rmk": r,
            "out": out_path, "placed": placed, "suma": round(suma, 2),
            "checksum_ok": abs(suma - check_target) < 0.005}
