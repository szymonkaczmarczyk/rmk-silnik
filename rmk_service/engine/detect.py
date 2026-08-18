"""Wykrywanie wystawcy faktury po treści (NIP / nazwa sprzedawcy)."""
import pdfplumber, re

SPRZEDAWCY = [
    ("Plus (Polkomtel)", ["POLKOMTEL", "527-10-37-727", "5271037727"]),
    ("T-Mobile",         ["T-Mobile Polska", "5261040567", "Marynarska 12"]),
    ("Orange",           ["Orange Polska", "5260250995"]),
    ("Play (P4)",        ["P4 Sp. z o.o.", "P4 Sp.z o.o", "5213000697", "6512987734", "Wynalazek 1"]),
    ("Integra (IDHosting)", ["IntegraDesign", "9491912205", "IDHosting"]),
    ("PremiumMobile",    ["Premium Mobile", "9542746551"]),
]

def detect_vendor(path):
    with pdfplumber.open(path) as pdf:
        txt = "\n".join((p.extract_text() or "") for p in pdf.pages[:3])
    low = txt.lower()
    for name, keys in SPRZEDAWCY:
        for k in keys:
            if k.lower() in low:
                return name
    return "??? nieznany"

def detect_buyer(path, nip_map):
    """Wykrywa spółkę-nabywcę po jej NIP obecnym w treści faktury.
    nip_map: {'7010489213': 'Faktury Confronter', ...}. Zwraca nazwę folderu lub None."""
    import re
    with pdfplumber.open(path) as pdf:
        txt = "\n".join((p.extract_text() or "") for p in pdf.pages[:3])
    digits = re.sub(r"\D", "", txt)
    for nip, folder in nip_map.items():
        if re.sub(r"\D", "", nip) in digits:
            return folder
    return None

if __name__ == "__main__":
    import glob, os
    base="/root/.claude/uploads/0067b073-b43a-5aac-83a4-ffaddfeb8301/rmk_extract/RMK"
    files=sorted(glob.glob(base+"/**/*.pdf", recursive=True))
    from collections import Counter
    c=Counter()
    for f in files:
        rel=os.path.relpath(f,base)
        # pomiń zeskanowane wzory (obrazy) w korzeniach spółek
        v=detect_vendor(f)
        c[v]+=1
        print(f"{v:22} | {rel}")
    print("\n=== PODSUMOWANIE ===")
    for k,n in c.most_common(): print(f"{n:3}  {k}")
