# RMK – automatyczne wyliczanie RMK z faktur telekom (Etap 2)

Silnik (Plus, Play, PremiumMobile, Integra, Orange, T-Mobile) + automatyka Drive/Gmail.
Wdrożenie krok-po-kroku: patrz **SETUP.md**.

- `rmk_service/engine/` – silnik RMK (parsery + podział + nakładka)
- `rmk_service/drive_sync.py` – pobiera z Bazowe, liczy, odkłada do Wyliczone
- `.github/workflows/rmk.yml` – harmonogram (co 15 min, darmowe)
- `apps_script/SaveAttachments.gs` – Gmail → Drive (Bazowe)
