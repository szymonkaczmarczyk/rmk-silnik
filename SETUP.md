# RMK – Etap 2: automatyka (darmowa, bez karty)

Cel: faktury lądują same → co ~15 min liczą się i trafiają do właściwej spółki i miesiąca.

Architektura:
```
Gmail (dedykowany) —filtr→ etykieta "RMK/do-zrobienia"
        │  Apps Script (co 10–15 min) zapisuje załączniki PDF
        ▼
Google Drive: RMK/_Poczta/  ──►  GitHub Actions (co 15 min, silnik Python)
                                    ├─ rozpoznaje spółkę (NIP nabywcy) i miesiąc (data wystawienia)
                                    ├─ surowiec → Faktury <Spółka>/Bazowe/<RRRR-MM>/
                                    └─ wynik    → Faktury <Spółka>/Wyliczone/<RRRR-MM>/
```
Wszystko darmowe, bez karty. Faktury są tylko na Drive — nigdy w GitHubie.

## Struktura folderów na Drive
```
RMK/
  _Poczta/                    ← tu ląduje poczta (silnik sam rozłoży)
  Faktury Confronter/
    Bazowe/     2026-08/ …
    Wyliczone/  2026-08/ …
  Faktury KSNBIZ/   (Bazowe/ Wyliczone/)
  Faktury TimeTo/   (Bazowe/ Wyliczone/)
  Faktury INVESTI-GATE/ (Bazowe/ Wyliczone/)
```
Możesz też wrzucać ręcznie prosto do `Faktury <Spółka>/Bazowe/<RRRR-MM>/` — silnik i tak policzy.
Foldery Bazowe/Wyliczone/miesiące powstaną same, jeśli ich nie ma.

---

## 1. Konto Google i folder RMK
1. Dedykowany Gmail (masz).
2. Utwórz w RMK podfolder **`_Poczta`** (jeśli chcesz automat z maila). Reszta (Bazowe/Wyliczone/miesiące) utworzy się sama.
3. Zapisz **ID folderu RMK** (z URL: `drive.google.com/drive/folders/<TO_JEST_ID>`).

## 2. OAuth — silnik loguje się JAKO dedykowany Gmail (darmowe, bez karty)
UWAGA: konto serwisowe NIE zadziała na zwykłym Gmailu (nie ma limitu miejsca, nie zapisze plików).
Dlatego używamy OAuth: silnik działa jako Twoje konto, pliki są Twoje (15 GB).
1. https://console.cloud.google.com → projekt „rmk" (masz). Karta NIE jest wymagana.
2. „APIs & Services" → włącz **Google Drive API**.
3. „OAuth consent screen": User type **External** → nazwa np. „RMK silnik", support/developer email = dedykowany Gmail →
   **Publish app → In production** (żeby refresh token nie wygasał po 7 dniach).
4. „Credentials" → „Create credentials" → **OAuth client ID** → typ **Desktop app** → pobierz JSON jako `client_secret.json`.
5. Lokalnie na komputerze (jednorazowo):
   ```
   pip install google-auth-oauthlib
   python rmk_service/get_refresh_token.py   # client_secret.json w tym samym folderze
   ```
   Zaloguj się dedykowanym Gmailem, zatwierdź dostęp (ekran „niezweryfikowana" → Zaawansowane → Przejdź).
   Skrypt wypisze CLIENT ID / CLIENT SECRET / REFRESH TOKEN.

## 3. Repozytorium GitHub + sekrety
1. Utwórz **publiczne** repo (np. `rmk-silnik`), wgraj `rmk_service/` i `.github/`.
2. Settings → Secrets and variables → Actions → dodaj cztery sekrety:
   - `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_REFRESH_TOKEN` (z kroku 2.5)
   - `RMK_ROOT_FOLDER_ID` – ID folderu RMK
3. Actions → uruchom „RMK – przeliczanie faktur" ręcznie („Run workflow"). Potem chodzi sam co 15 min.

## 4. Gmail → Drive (Apps Script) — jeśli chcesz automat z maila
1. Gmail: utwórz **filtr** (po nadawcy / tytule) → akcja „Zastosuj etykietę: `RMK/do-zrobienia`".
2. https://script.google.com → nowy projekt → wklej `apps_script/SaveAttachments.gs`,
   ustaw `POCZTA_FOLDER_ID` = ID folderu `RMK/_Poczta`.
3. Uruchom raz `zapiszZalaczniki` (zaakceptuj uprawnienia) → „Triggers" → wyzwalacz czasowy co 10 min.
4. `home.pl`: reguła przekierowująca wskazane maile na dedykowanego Gmaila.

## 5. Test
- Wrzuć kilka PDF do `RMK/_Poczta` (lub prosto do `Faktury <Spółka>/Bazowe/<RRRR-MM>/`).
- Odpal workflow ręcznie → pliki rozłożą się po spółkach/miesiącach, a wyniki `<nazwa>_wyliczone.pdf`
  pojawią się w `Wyliczone`. Ponowne uruchomienia pomijają już przeliczone.

## Uwagi
- Mapowanie NIP→spółka jest w `rmk_service/engine/config.json` (klucz `spolki_nip`) — łatwo dodać spółkę.
- Miesiąc = data wystawienia faktury (`RRRR-MM`).
- Krok „dopisywanie kwot do pliku master" dojdzie po uruchomieniu obiegu.
