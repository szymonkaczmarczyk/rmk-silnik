"""RMK core: podział kwoty netto na miesiące wg dni okresu rozliczeniowego."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import calendar

ROMAN = {1:"I",2:"II",3:"III",4:"IV",5:"V",6:"VI",7:"VII",8:"VIII",9:"IX",10:"X",11:"XI",12:"XII"}

def q2(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def month_spans(start: date, end: date):
    """Zwraca listę (rok, miesiąc, liczba_dni_okresu_w_tym_miesiacu). Okres [start, end] włącznie."""
    spans = []
    cur = start
    while cur <= end:
        last_dom = calendar.monthrange(cur.year, cur.month)[1]
        month_end = date(cur.year, cur.month, last_dom)
        seg_end = min(month_end, end)
        days = (seg_end - cur).days + 1
        spans.append((cur.year, cur.month, days))
        cur = seg_end + timedelta(days=1)
    return spans

def split_rmk(netto, start: date, end: date):
    """Dzieli netto na miesiące: netto/dni_okresu * dni_w_miesiacu. Reszta zaokrągleń -> ostatni miesiac."""
    netto = Decimal(str(netto))
    spans = month_spans(start, end)
    total_days = sum(d for _,_,d in spans)
    daily = netto / Decimal(total_days)
    rows = []
    running = Decimal("0.00")
    for i,(y,m,d) in enumerate(spans):
        if i < len(spans)-1:
            amt = q2(daily * d)
        else:
            amt = q2(netto) - running   # ostatni = reszta, suma == netto
        running += amt
        rows.append({"rok":y, "mies":m, "roman":ROMAN[m], "dni":d, "kwota":amt})
    return {"netto":q2(netto), "total_days":total_days, "rows":rows}

if __name__ == "__main__":
    # test wg wzorca Plus: 180,00 za okres 25.07-24.08
    r = split_rmk("180.00", date(2026,7,25), date(2026,8,24))
    for row in r["rows"]:
        print(f"{row['roman']}: {r['netto']} : {r['total_days']} x {row['dni']} = {row['kwota']}")
    print("suma:", sum(x['kwota'] for x in r['rows']))
