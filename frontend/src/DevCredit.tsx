// Mention « Développé par BWETEK Informatyk » avec le logo de l'éditeur, en bas de chaque page.
import bwetekUrl from "./assets/logo-bwetek.png";
import { tr } from "./i18n";

export function DevCredit() {
  return (
    <footer className="dev-credit">
      <img src={bwetekUrl} alt="" />
      <span>{tr("footer.developedBy")}</span>
    </footer>
  );
}
