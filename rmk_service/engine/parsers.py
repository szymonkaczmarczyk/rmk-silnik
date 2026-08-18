"""Parsery per wystawca. Wspólny zwracany słownik:
   {wystawca, nr_faktury, data_wystawienia, okres_od, okres_do, netto, uwagi}
Integra: okres = data sprzedaży -> koniec tego miesiąca (pojedynczy miesiąc).
"""
import re, pdfplumber, calendar
from datetime import date

def num(s):
    """'1 365,30' / '1.365,30' / '450,00' -> float"""
    s = s.replace(" ", "").replace("\xa0", "")
    s = s.replace(".", "") if re.search(r",\d{2}$", s) else s
    return float(s.replace(",", "."))

def d_dot(s):  # DD.MM.YYYY
    dd, mm, yy = s.split("."); return date(int(yy), int(mm), int(dd))
def d_iso(s):  # YYYY-MM-DD
    yy, mm, dd = s.split("-"); return date(int(yy), int(mm), int(dd))
def d_dash(s): # DD-MM-YYYY
    dd, mm, yy = s.split("-"); return date(int(yy), int(mm), int(dd))

def eom(dt):
    return date(dt.year, dt.month, calendar.monthrange(dt.year, dt.month)[1])

def _text(path, n=None):
    with pdfplumber.open(path) as pdf:
        pgs = pdf.pages if n is None else pdf.pages[:n]
        return "\n".join((p.extract_text() or "") for p in pgs)

# ---------- PremiumMobile ----------
def parse_premium(path):
    t = _text(path, 3)
    nr = re.search(r"Faktura nr\s+(\S+)", t)
    dw = re.search(r"Data wystawienia\s+(\d{4}-\d{2}-\d{2})", t)
    per = re.search(r"Abonamenty za\s+(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})", t)
    net = re.search(r"Abonamenty\s+([\d \xa0]+,\d{2})\s+\d", t)
    return {"wystawca":"PremiumMobile","nr_faktury":nr.group(1) if nr else None,
            "data_wystawienia":d_iso(dw.group(1)) if dw else None,
            "okres_od":d_iso(per.group(1)), "okres_do":d_iso(per.group(2)),
            "netto":round(num(net.group(1)),2), "uwagi":""}

# ---------- Integra ----------
def parse_integra(path):
    t = _text(path, 1)
    nr = re.search(r"Faktura VAT nr\s+(\S+)", t)
    ds = re.search(r"Data sprzedaży:\s*(\d{2}-\d{2}-\d{4})", t)
    net = re.search(r"Razem:\s*([\d \xa0]+,\d{2})", t)
    from datetime import timedelta
    sprzedazy = d_dash(ds.group(1))
    okres_do = shift_month(sprzedazy, 1) - timedelta(days=1)  # dzień poprzedzający w następnym miesiącu
    return {"wystawca":"Integra (IDHosting)","nr_faktury":nr.group(1) if nr else None,
            "data_wystawienia":sprzedazy, "data_sprzedazy":sprzedazy,
            "okres_od":sprzedazy, "okres_do":okres_do,
            "netto":round(num(net.group(1)),2),
            "uwagi":"okres = data sprzedaży -> dzień poprzedzający w następnym miesiącu (2 miesiące)"}

# ---------- Play (P4) ----------
def parse_play(path):
    t = _text(path, 2)
    nr = re.search(r"[Ff]aktura VAT nr\s+(\S+)|Numer faktury\s+(\S+)", t)
    nrv = next((g for g in (nr.groups() if nr else []) if g), None)
    dw = re.search(r"Data wystawienia:?\s*(\d{2}\.\d{2}\.\d{4})", t)
    # Layout A: "Abonament za okres DD.MM.YYYY – DD.MM.YYYY"
    a = re.search(r"Abonament za okres\s*\n?\s*(\d{2}\.\d{2}\.\d{4})\s*[–\-]\s*(\d{2}\.\d{2}\.\d{4})", t)
    if a:
        net = re.search(r"Usługi telekomunikacyjne\s+([\d \xa0]+,\d{2})", t) \
              or re.search(r"\n([\d \xa0]+,\d{2})\s+\d+%?\s*[\d \xa0]+,\d{2}\s+[\d \xa0]+,\d{2}\s*\nWARTOŚĆ", t)
        return {"wystawca":"Play (P4)","nr_faktury":nrv,
                "data_wystawienia":d_dot(dw.group(1)) if dw else None,
                "okres_od":d_dot(a.group(1)),"okres_do":d_dot(a.group(2)),
                "netto":round(num(net.group(1)),2),"uwagi":"szablon A (Abonament za okres)"}
    # Layout B: tabela "od DD.MM.YYYY do DD.MM.YYYY" + "Razem: netto"
    b = re.search(r"od\s+(\d{2}\.\d{2}\.\d{4})\s*.*?do\s+(\d{2}\.\d{2}\.\d{4})", t, re.S)
    net = re.search(r"Razem:\s*([\d \xa0]+,\d{2})", t)
    return {"wystawca":"Play (P4)","nr_faktury":nrv,
            "data_wystawienia":d_dot(dw.group(1)) if dw else None,
            "okres_od":d_dot(b.group(1)),"okres_do":d_dot(b.group(2)),
            "netto":round(num(net.group(1)),2),"uwagi":"szablon B (tabela od-do)"}

PARSERS = {
    "PremiumMobile": parse_premium,
    "Integra (IDHosting)": parse_integra,
    "Play (P4)": parse_play,
}

# ---------- wspólne: polskie miesiące, przesunięcie o miesiąc ----------
PL_MIES = {"stycznia":1,"lutego":2,"marca":3,"kwietnia":4,"maja":5,"czerwca":6,
           "lipca":7,"sierpnia":8,"września":9,"wrzesnia":9,"października":10,"pazdziernika":10,
           "listopada":11,"grudnia":12}

def d_pl(s):  # "10 lipca 2026"
    m = re.search(r"(\d{1,2})\s+([a-ząćęłńóśżź]+)\s+(\d{4})", s.lower())
    dd, mon, yy = int(m.group(1)), PL_MIES[m.group(2)], int(m.group(3))
    return date(yy, mon, dd)

def shift_month(dt, k=1):
    m = dt.month - 1 + k
    y = dt.year + m // 12
    m = m % 12 + 1
    d = min(dt.day, calendar.monthrange(y, m)[1])
    return date(y, m, d)

def _norm_digits(s):
    return re.sub(r"\D", "", s)

# ---------- Orange ----------
def parse_orange(path, excluded=None):
    excluded = set(_norm_digits(x) for x in (excluded or []))
    t = _text(path)
    nr = re.search(r"Numer:\s*(\d+)", t)
    dw = re.search(r"Data wystawienia:\s*([0-9]{1,2}\s+\w+\s+\d{4})", t)
    data_wyst = d_pl(dw.group(1))
    okr = re.search(r"Okres rozliczeniowy:\s*(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})", t)
    p_od = d_dot_flex(okr.group(1)); p_do = d_dot_flex(okr.group(2))
    # RMK liczymy od okresu abonamentu = nadrukowany okres + 1 miesiąc
    okres_od, okres_do = shift_month(p_od, 1), shift_month(p_do, 1)
    total = re.search(r"Usługi mobilne Orange\s+([\d \xa0]+,\d{2})", t)
    netto_total = round(num(total.group(1)), 2)
    # numery wyłączone: linia podsumowania "<numer> <netto> <brutto>"
    wyl = []
    for m in re.finditer(r"(?m)^\s*(\d{9,11})\s+(-?[\d \xa0]+,\d{2})\s+(-?[\d \xa0]+,\d{2})\s*$", t):
        if _norm_digits(m.group(1)) in excluded:
            wyl.append({"numer": m.group(1), "netto": round(num(m.group(2)), 2)})
    excl_sum = round(sum(w["netto"] for w in wyl), 2)
    return {"wystawca":"Orange","nr_faktury":nr.group(1) if nr else None,
            "data_wystawienia":data_wyst,"okres_od":okres_od,"okres_do":okres_do,
            "netto":round(netto_total - excl_sum, 2),   # baza do podziału
            "netto_total":netto_total,"wylaczone":wyl,"excl_sum":excl_sum,
            "uwagi":"okres = nadrukowany +1 miesiąc; numery wyłączone dodane do miesiąca wystawienia"}

def d_dot_flex(s):  # 9.07.2026 lub 10.06.2026
    dd, mm, yy = s.split("."); return date(int(yy), int(mm), int(dd))

# ---------- T-Mobile ----------
def parse_tmobile(path):
    t = _text(path)
    nr = re.search(r"Numer faktury:\s*(\d+)", t)
    dw = re.search(r"[Dd]ata wystawienia[:\s]*?(\d{2}\.\d{2}\.\d{4})", t)
    okr = re.search(r"Okres rozliczeniowy:\s*(\d{2}\.\d{2}\.\d{4})\s*[–-]\s*(\d{2}\.\d{2}\.\d{4})", t)
    p_od, p_do = d_dot(okr.group(1)), d_dot(okr.group(2))
    suma = re.search(r"SUMA:\s*(-?[\d ]+,\d{2}) zł\s*(-?[\d ]+,\d{2}) zł\s*(-?[\d ]+,\d{2}) zł\s*(-?[\d ]+,\d{2}) zł\s*(-?[\d ]+,\d{2}) zł\s*(-?[\d ]+,\d{2}) zł", t)
    abon, rab, a2, a3, nieobj, razem_br = [num(x) for x in suma.groups()]
    total_net = round(abon + rab + a2 + a3, 2)   # netto do RMK (bez 'opłat nieobjętych' VAT)

    okres_od, okres_do = shift_month(p_od,1), shift_month(p_do,1)   # bieżący abonament = nadrukowany +1 mies.

    # Klasyfikacja pozycji PO OKRESIE: bieżący okres = do podziału; reszta = poprzedni okres -> 1. miesiąc.
    biezacy = round(sum(num(a) for a in re.findall(
        rf"{okres_od.strftime('%d.%m.%Y')}[–-]{okres_do.strftime('%d.%m.%Y')}\s+(-?[\d ]+,\d{{2}})", t)), 2)
    poprzedni = round(total_net - biezacy, 2)   # korzystanie + inne z poprzedniego okresu

    # dla etykiety: "Opłata za korzystanie"
    kor = re.findall(r"Opłata za korzystanie.*?(\d{2}\.\d{2}\.\d{4})[–-](\d{2}\.\d{2}\.\d{4})\s+(-?[\d ]+,\d{2})", t)
    korzystanie = round(sum(num(k[2]) for k in kor), 2)
    kor_okres = (d_dot(kor[0][0]), d_dot(kor[0][1])) if kor else None

    return {"wystawca":"T-Mobile","nr_faktury":nr.group(1) if nr else None,
            "data_wystawienia": d_dot(dw.group(1)) if dw else p_do,
            "okres_od": okres_od, "okres_do": okres_do,
            "printed_od": p_od, "printed_do": p_do,
            "netto": biezacy,               # baza do podziału (pozycje bieżącego okresu)
            "poprzedni_okres": poprzedni,   # do 1. miesiąca
            "korzystanie": korzystanie, "kor_okres": kor_okres,
            "total_net": total_net,
            "uwagi":"pozycje bieżącego okresu dzielone; pozycje poprzedniego okresu -> 1. miesiąc"}
