"""Parser faktur Plus/Polkomtel — obsługa WIELU okresów rozliczeniowych na jednej fakturze.
Baza = netto po rabatach. Każdy numer ma 1..n pozycji (abonament/inne) z własnym okresem;
rabaty per numer; rabat konta rozłożony proporcjonalnie (przez skalowanie do 'Bieżące opłaty dla konta - łącznie').
Zwraca listę okresów: [{'od','do','netto'}] zagregowaną po okresie.
"""
import re, pdfplumber
from collections import defaultdict
from datetime import date

def _d(s):
    dd, mm, yy = re.split(r"[.\-/]", s.strip()); return date(int(yy), int(mm), int(dd))

def _num(s):
    return float(s.replace(" ", "").replace("\xa0", "").replace(",", "."))

def parse_plus(path):
    with pdfplumber.open(path) as pdf:
        full = "\n".join((p.extract_text() or "") for p in pdf.pages)

    nrfa = re.search(r"FAKTURA VAT\s*\n?\s*nr\s*([0-9]+)", full)
    dw = re.search(r"Data wystawienia faktury\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})", full)

    # total netto po rabatach
    m = re.search(r"Bieżące opłaty dla konta\s*-\s*łącznie\s+([\d \xa0]+,\d{2})", full)
    if not m:
        m = re.search(r"\nRazem\s+([\d \xa0]+,\d{2})\s+[\d \xa0]+,\d{2}\s+[\d \xa0]+,\d{2}", full)
    total_net = round(_num(m.group(1)), 2)

    # --- pozycje z okresem (abonament + inne usługi): (numer, od, do, gross) ---
    gross_by_num = defaultdict(lambda: defaultdict(float))   # numer -> (od,do) -> gross
    cur_num = None
    line_re = re.compile(r"(\d{2}\.\d{2}\.\d{4})\s+do\s+(\d{2}\.\d{2}\.\d{4})\s+([\d \xa0]+,\d{2})\s+[\d \xa0]+,\d{2}\s*$")
    numstart_re = re.compile(r"^(\d{9})\b")
    for ln in full.splitlines():
        mm = line_re.search(ln)
        if not mm:
            continue
        ns = numstart_re.match(ln.strip())
        if ns:
            cur_num = ns.group(1)
        if cur_num is None:
            continue
        od, do, gross = _d(mm.group(1)), _d(mm.group(2)), _num(mm.group(3))
        gross_by_num[cur_num][(od, do)] += gross

    # --- rabaty per numer ---
    rab_by_num = defaultdict(float)
    for ln in full.splitlines():
        rm = re.match(r"^(\d{9})\s+Rabat\S.*?(-[\d \xa0]+,\d{2})\s+-[\d \xa0]+,\d{2}\s*$", ln.strip())
        if rm:
            rab_by_num[rm.group(1)] += _num(rm.group(2))

    if not gross_by_num:
        raise ValueError("Nie znaleziono pozycji abonamentu z okresem")

    # --- net per numer, alokacja na okresy proporcjonalnie do gross ---
    net_by_period = defaultdict(float)
    for num, per in gross_by_num.items():
        g_tot = sum(per.values())
        net_num = g_tot + rab_by_num.get(num, 0.0)   # po rabatach per numer
        if g_tot == 0:
            continue
        for (od, do), g in per.items():
            net_by_period[(od, do)] += net_num * (g / g_tot)

    # --- skalowanie do total_net (absorbuje rabat konta i drobne różnice) ---
    raw = sum(net_by_period.values())
    scale = (total_net / raw) if raw else 1.0
    periods = [{"od": od, "do": do, "netto": round(v * scale, 2)}
               for (od, do), v in sorted(net_by_period.items())]
    # korekta grosza: suma okresów == total_net
    diff = round(total_net - sum(p["netto"] for p in periods), 2)
    if periods and diff:
        periods[max(range(len(periods)), key=lambda i: periods[i]["netto"])]["netto"] += diff

    okres_od = min(p["od"] for p in periods); okres_do = max(p["do"] for p in periods)
    return {
        "wystawca": "Plus (Polkomtel)",
        "nr_faktury": nrfa.group(1) if nrfa else None,
        "data_wystawienia": _d(dw.group(1)) if dw else None,
        "okres_od": okres_od, "okres_do": okres_do,   # zakres łączny (informacyjnie)
        "netto": total_net,
        "periods": periods,
        "uwagi": f"{len(periods)} okres(ów); netto po rabatach; rabat per numer proporcjonalnie",
    }

if __name__ == "__main__":
    import sys
    r = parse_plus(sys.argv[1])
    print("total:", r["netto"], "| okresów:", len(r["periods"]))
    for p in r["periods"]:
        print(f"   {p['od']} → {p['do']}: {p['netto']}")
