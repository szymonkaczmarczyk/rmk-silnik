"""Jednorazowo, LOKALNIE na Twoim komputerze: generuje refresh token do Drive.

Wymaga:
  pip install google-auth-oauthlib
  plik client_secret.json (pobrany z Google Cloud → OAuth client, typ Desktop) w tym samym folderze.

Uruchom:  python get_refresh_token.py
Otworzy przeglądarkę → zaloguj się na DEDYKOWANY Gmail (faktury.rmk.confronter@…) i zatwierdź dostęp.
Na końcu wypisze CLIENT ID / CLIENT SECRET / REFRESH TOKEN — wklej je do sekretów GitHuba.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    print("\n==== WKLEJ DO SEKRETÓW GITHUBA ====")
    print("OAUTH_CLIENT_ID     =", creds.client_id)
    print("OAUTH_CLIENT_SECRET =", creds.client_secret)
    print("OAUTH_REFRESH_TOKEN =", creds.refresh_token)
    if not creds.refresh_token:
        print("\n[!] Brak refresh tokenu — usuń wcześniejszy dostęp aplikacji na "
              "myaccount.google.com/permissions i uruchom ponownie (musi być access_type=offline + prompt=consent).")

if __name__ == "__main__":
    main()
