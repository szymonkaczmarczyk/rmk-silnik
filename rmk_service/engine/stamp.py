"""Nanosi wyliczenie RMK na PDF (nakładka na 1. stronie, niebieski). Fallback: pusta strona."""
import pymupdf
from decimal import Decimal

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BLUE = (0.0, 0.15, 0.7)

def pln(x):
    return f"{Decimal(str(x)):.2f}".replace(".", ",")

def build_lines(parsed, rmk):
    # jeśli wystawca dostarczył własne linie (Orange/T-Mobile) — użyj ich
    if parsed.get("overlay_lines"):
        return parsed["overlay_lines"]
    lines = [("RMK:", True)]
    n = pln(rmk["netto"]); td = rmk["total_days"]
    for row in rmk["rows"]:
        lines.append((f"{row['roman']}: {n} : {td} × {row['dni']} = {pln(row['kwota'])} zł", False))
    suma = pln(sum(r["kwota"] for r in rmk["rows"]))
    lines.append((f"razem: {suma} zł", True))
    return lines

def _txt(page, pos, s, font, size, color):
    tw = pymupdf.TextWriter(page.rect)
    tw.append(pos, s, font=font, fontsize=size)
    tw.write_text(page, color=color)

def _obstacles(page):
    """Zbiera bboxy wszystkiego, co zajęte: słowa, obrazy, rysunki."""
    obs = []
    for w in page.get_text("words"):
        obs.append(pymupdf.Rect(w[:4]))
    for im in page.get_images(full=True):
        for r in page.get_image_rects(im[0]):
            obs.append(r)
    for d in page.get_drawings():
        obs.append(pymupdf.Rect(d["rect"]))
    return obs

def find_free_rect(page, w, h, pad=6, margin=24, cell=4):
    """Znajduje wolny prostokąt w×h (pt) najdalej od zajętych obszarów. None jeśli brak."""
    import numpy as np
    from scipy import ndimage
    W, H = page.rect.width, page.rect.height
    gw, gh = int(np.ceil(W/cell)), int(np.ceil(H/cell))
    occ = np.zeros((gh, gw), dtype=np.uint8)
    for r in _obstacles(page):
        x0=max(0,int((r.x0-pad)//cell)); y0=max(0,int((r.y0-pad)//cell))
        x1=min(gw,int((r.x1+pad)//cell)+1); y1=min(gh,int((r.y1+pad)//cell)+1)
        if x1>x0 and y1>y0: occ[y0:y1, x0:x1]=1
    m=int(margin//cell)
    occ[:m,:]=1; occ[-m:,:]=1; occ[:,:m]=1; occ[:,-m:]=1
    free=(occ==0)
    # integral image do szybkiego testu pustości okna
    integ=np.zeros((gh+1,gw+1),dtype=np.int32); integ[1:,1:]=np.cumsum(np.cumsum(occ,0),1)
    bw,bh=int(np.ceil(w/cell)),int(np.ceil(h/cell))
    if bw>=gw or bh>=gh: return None
    dist=ndimage.distance_transform_edt(free)
    best=None; best_score=-1
    for yy in range(0, gh-bh):
        for xx in range(0, gw-bw):
            s=integ[yy+bh,xx+bw]-integ[yy,xx+bw]-integ[yy+bh,xx]+integ[yy,xx]
            if s!=0: continue
            score=dist[yy+bh//2, xx+bw//2]
            if score>best_score:
                best_score=score; best=(xx*cell, yy*cell)
    return best

def _draw_box(page, x, y, lines, freg, fbold, lh=15, fs=11):
    maxw = max((fbold if b else freg).text_length(t, fs) for t,b in lines)
    page.draw_rect(pymupdf.Rect(x-12, y-24, x+maxw+16, y+lh*len(lines)+4), color=BLUE, width=0.9, fill=(0.96,0.97,1.0))
    for i,(txt,bold) in enumerate(lines):
        _txt(page,(x, y+i*lh), txt, (fbold if bold else freg), fs, BLUE)

def stamp(in_path, out_path, parsed, rmk, mode="auto"):
    """mode: 'auto' = inteligentna nakładka na 1. str., a jak brak miejsca -> okładka; 'cover' = zawsze okładka."""
    doc = pymupdf.open(in_path)
    freg = pymupdf.Font(fontfile=FONT)
    fbold = pymupdf.Font(fontfile=FONTB)
    lines = build_lines(parsed, rmk)
    lh, fs = 15, 11
    placed = "cover"
    if mode != "cover":
        page = doc[0]
        box_w = max((fbold if b else freg).text_length(t, fs) for t,b in lines) + 30
        box_h = lh*len(lines) + 30
        spot = find_free_rect(page, box_w, box_h)
        if spot:
            _draw_box(page, spot[0]+12, spot[1]+24, lines, freg, fbold, lh, fs)
            placed = "overlay"
    if placed == "cover":
        page = doc.new_page(0, width=595, height=842)
        x = 60
        _txt(page,(x,90), f"Wyliczenie RMK — {parsed['wystawca']}", fbold, 14, BLUE)
        _txt(page,(x,110), f"Faktura {parsed.get('nr_faktury','')}   okres {parsed['okres_od'].strftime('%d.%m.%Y')}–{parsed['okres_do'].strftime('%d.%m.%Y')}", freg, 9, (0.2,0.2,0.2))
        page.draw_line(pymupdf.Point(x,124), pymupdf.Point(x+320,124), color=BLUE, width=0.6)
        _draw_box(page, x, 150, lines, freg, fbold, lh, fs)
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return placed
