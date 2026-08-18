/**
 * RMK – zapisywanie załączników z Gmaila do folderu "Bazowe" na Drive.
 *
 * Jak działa:
 *  - przetwarza wątki z etykietą ETYKIETA_DO_ZROBIENIA (ustaw filtr w Gmailu, który
 *    nakłada tę etykietę na maile z fakturami – po nadawcy lub tytule),
 *  - zapisuje WSZYSTKIE załączniki PDF do folderu wejściowego POCZTA_FOLDER_ID (RMK/_Poczta),
 *  - po zapisaniu zdejmuje etykietę "do zrobienia" i nakłada "zapisane" (bez duplikatów).
 *
 * Silnik (GitHub Actions) sam rozpozna spółkę (po NIP) i miesiąc, i rozłoży pliki po folderach.
 * Uruchamianie: ustaw wyzwalacz czasowy (Triggers) na funkcję zapiszZalaczniki, np. co 10–15 min.
 */

const POCZTA_FOLDER_ID       = "WKLEJ_ID_FOLDERU__Poczta";
const ETYKIETA_DO_ZROBIENIA  = "RMK";
const ETYKIETA_ZAPISANE      = "RMK-zapisane";

function zapiszZalaczniki() {
  const folder = DriveApp.getFolderById(POCZTA_FOLDER_ID);
  const todo   = GmailApp.getUserLabelByName(ETYKIETA_DO_ZROBIENIA);
  const done   = GmailApp.getUserLabelByName(ETYKIETA_ZAPISANE)
                 || GmailApp.createLabel(ETYKIETA_ZAPISANE);
  if (!todo) { Logger.log("Brak etykiety " + ETYKIETA_DO_ZROBIENIA); return; }

  const watki = todo.getThreads(0, 50);
  for (const watek of watki) {
    let zapisano = 0;
    for (const msg of watek.getMessages()) {
      for (const att of msg.getAttachments()) {
        const nazwa = att.getName() || "";
        const pdf = att.getContentType() === "application/pdf"
                 || nazwa.toLowerCase().endsWith(".pdf");
        if (!pdf) continue;
        if (istniejeJuz(folder, nazwa)) continue;   // bez duplikatów
        folder.createFile(att.copyBlob()).setName(nazwa);
        zapisano++;
      }
    }
    watek.addLabel(done);
    watek.removeLabel(todo);
    Logger.log("Wątek: zapisano " + zapisano + " PDF");
  }
}

function istniejeJuz(folder, nazwa) {
  const it = folder.getFilesByName(nazwa);
  return it.hasNext();
}
