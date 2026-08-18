"""RMK Drive sync — polluje folder 'Bazowe' na Google Drive, liczy RMK i odkłada do 'Wyliczone'.
Uruchamiany cyklicznie przez GitHub Actions. Autoryzacja: konto serwisowe (bez karty, Drive API).

Idempotentny: dla pliku Bazowe/<ścieżka>/<nazwa>.pdf tworzy Wyliczone/<ścieżka>/<nazwa>_wyliczone.pdf.
Jeśli wynik już istnieje (i źródło się nie zmieniło) — pomija.

Obsługuje wiele spółek: znajduje KAŻDY folder o nazwie 'Bazowe' pod korzeniem RMK
i odkłada wyniki do sąsiedniego 'Wyliczone' (tworzy go, jeśli brak), zachowując podfoldery
(np. miesiące). Struktura: RMK/Faktury <Spółka>/Bazowe/<2026-08>/  →  .../Wyliczone/<2026-08>/.

Autoryzacja: OAuth jako dedykowany Gmail (refresh token) — pliki należą do konta użytkownika
(normalne 15 GB), więc działa na zwykłym Gmailu. Konto serwisowe NIE działa (brak limitu miejsca).

ENV:
  OAUTH_CLIENT_ID       – Client ID z OAuth clienta (typ Desktop)
  OAUTH_CLIENT_SECRET   – Client Secret
  OAUTH_REFRESH_TOKEN   – refresh token (z get_refresh_token.py, uruchom raz lokalnie)
  RMK_ROOT_FOLDER_ID    – ID folderu 'RMK' (korzeń, w którym są foldery spółek)
"""
import os, io, json, sys, tempfile, traceback
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "engine"))
from pipeline import process   # silnik RMK
from detect import detect_buyer

_ENGINE_CFG = json.load(open(os.path.join(os.path.dirname(__file__), "engine", "config.json")))
NIP_MAP = _ENGINE_CFG.get("spolki_nip", {})

SCOPES = ["https://www.googleapis.com/auth/drive"]

def svc():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["OAUTH_REFRESH_TOKEN"],
        client_id=os.environ["OAUTH_CLIENT_ID"],
        client_secret=os.environ["OAUTH_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def list_children(drive, folder_id, mime=None):
    q = f"'{folder_id}' in parents and trashed=false"
    if mime: q += f" and mimeType='{mime}'"
    out, tok = [], None
    while True:
        r = drive.files().list(q=q, fields="nextPageToken, files(id,name,mimeType,modifiedTime)",
                               pageToken=tok, pageSize=1000).execute()
        out += r.get("files", [])
        tok = r.get("nextPageToken")
        if not tok: break
    return out

def walk_pdfs(drive, folder_id, rel=""):
    """Rekurencyjnie: (plik_pdf, ścieżka_względna_folderu)."""
    for f in list_children(drive, folder_id):
        if f["mimeType"] == "application/vnd.google-apps.folder":
            yield from walk_pdfs(drive, f["id"], os.path.join(rel, f["name"]))
        elif f["name"].lower().endswith(".pdf"):
            yield f, rel

def ensure_path(drive, root_id, rel):
    """Tworzy (lub znajduje) podfoldery rel pod root_id, zwraca ID najgłębszego."""
    cur = root_id
    for part in [p for p in rel.split(os.sep) if p]:
        found = [c for c in list_children(drive, cur,
                 "application/vnd.google-apps.folder") if c["name"] == part]
        if found:
            cur = found[0]["id"]
        else:
            meta = {"name": part, "mimeType": "application/vnd.google-apps.folder", "parents": [cur]}
            cur = drive.files().create(body=meta, fields="id").execute()["id"]
    return cur

def download(drive, file_id, dest):
    req = drive.files().get_media(fileId=file_id)
    with io.FileIO(dest, "wb") as fh:
        dl = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = dl.next_chunk()

def upload(drive, path, name, parent_id):
    media = MediaFileUpload(path, mimetype="application/pdf", resumable=False)
    meta = {"name": name, "parents": [parent_id]}
    return drive.files().create(body=meta, media_body=media, fields="id").execute()["id"]

def find_bazowe_pairs(drive, root_id, path=""):
    """Znajduje pary (bazowe_id, wyliczone_id, etykieta) pod korzeniem RMK."""
    pairs = []
    for f in list_children(drive, root_id, "application/vnd.google-apps.folder"):
        p = os.path.join(path, f["name"])
        if f["name"].lower() == "bazowe":
            parent = root_id
            sib = [c for c in list_children(drive, parent, "application/vnd.google-apps.folder")
                   if c["name"].lower() == "wyliczone"]
            wid = sib[0]["id"] if sib else drive.files().create(
                body={"name": "Wyliczone", "mimeType": "application/vnd.google-apps.folder",
                      "parents": [parent]}, fields="id").execute()["id"]
            pairs.append((f["id"], wid, path or "RMK"))
        else:
            pairs += find_bazowe_pairs(drive, f["id"], p)
    return pairs

def move_file(drive, file_id, new_parent, old_parent):
    drive.files().update(fileId=file_id, addParents=new_parent,
                         removeParents=old_parent, fields="id").execute()

def find_child_folder(drive, parent_id, name):
    hits = [c for c in list_children(drive, parent_id, "application/vnd.google-apps.folder")
            if c["name"].lower() == name.lower()]
    return hits[0]["id"] if hits else None

def handle_inbox(drive, root):
    """Sortuje folder wejściowy '_Poczta': wykrywa spółkę (NIP) i miesiąc (data wystawienia),
    przenosi surowiec do Faktury <Spółka>/Bazowe/<RRRR-MM> i odkłada wynik do .../Wyliczone/<RRRR-MM>."""
    poczta = find_child_folder(drive, root, "_Poczta") or find_child_folder(drive, root, "Poczta")
    if not poczta:
        return 0, 0
    sorted_n = unknown = 0
    for f in list_children(drive, poczta):
        if not f["name"].lower().endswith(".pdf"):
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                src = os.path.join(td, f["name"])
                download(drive, f["id"], src)
                res = process(src, td)
                buyer = detect_buyer(src, NIP_MAP)
                dw = res.get("parsed", {}).get("data_wystawienia")
                if not buyer or not dw:
                    print(f"[_Poczta] nie rozpoznano {'spółki' if not buyer else 'daty'}: {f['name']}")
                    unknown += 1; continue
                month = dw.strftime("%Y-%m")
                spolka = ensure_path(drive, root, buyer)
                bazowe = ensure_path(drive, spolka, os.path.join("Bazowe", month))
                wyliczone = ensure_path(drive, spolka, os.path.join("Wyliczone", month))
                # wynik -> Wyliczone/<miesiąc>
                out_name = f"{os.path.splitext(f['name'])[0]}_wyliczone.pdf"
                if not [c for c in list_children(drive, wyliczone) if c["name"] == out_name]:
                    upload(drive, res["out"], out_name, wyliczone)
                # surowiec -> Bazowe/<miesiąc>
                move_file(drive, f["id"], bazowe, poczta)
                print(f"[_Poczta] {f['name']} -> {buyer}/{month} ({res['vendor']})")
                sorted_n += 1
        except Exception as e:
            unknown += 1
            print(f"[_Poczta BŁĄD] {f['name']}: {e}")
            traceback.print_exc()
    return sorted_n, unknown

def main():
    drive = svc()
    root = os.environ["RMK_ROOT_FOLDER_ID"]
    isort, iunk = handle_inbox(drive, root)
    if isort or iunk:
        print(f"_Poczta: posortowano {isort}, nierozpoznane {iunk}.")
    pairs = find_bazowe_pairs(drive, root)
    print(f"Znaleziono {len(pairs)} folder(ów) 'Bazowe'.")
    done = errs = skipped = 0
    for bazowe, wyliczone, label in pairs:
        for f, rel in walk_pdfs(drive, bazowe):
            base = os.path.splitext(f["name"])[0]
            out_name = f"{base}_wyliczone.pdf"
            target_folder = ensure_path(drive, wyliczone, rel)
            if [c for c in list_children(drive, target_folder) if c["name"] == out_name]:
                skipped += 1
                continue
            tag = f"{label}/{rel}/{f['name']}".replace("//", "/")
            try:
                with tempfile.TemporaryDirectory() as td:
                    src = os.path.join(td, f["name"])
                    download(drive, f["id"], src)
                    res = process(src, td)
                    if not res.get("ok"):
                        print(f"[POMIŃ] {tag}: {res.get('reason')} ({res.get('vendor')})")
                        skipped += 1; continue
                    if not res.get("checksum_ok"):
                        print(f"[UWAGA] {tag}: suma != netto")
                    upload(drive, res["out"], out_name, target_folder)
                    print(f"[OK] {tag} -> {res['vendor']} ({res['placed']})")
                    done += 1
            except Exception as e:
                errs += 1
                print(f"[BŁĄD] {tag}: {e}")
                traceback.print_exc()
    print(f"\nGotowe: {done} przeliczone, {skipped} pominięte, {errs} błędy.")
    if errs: sys.exit(1)

if __name__ == "__main__":
    main()
