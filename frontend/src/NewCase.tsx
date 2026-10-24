// Écran « Nouveau dossier » : formulaire en sections, résumé à droite, pièces initiales jointes à la création.
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api, ApiError, type Importer, type Me, type Membership } from "./api";
import { canEditCases } from "./Cases";
import { Icon, type IconName } from "./Icon";
import { navigate } from "./router";
import { errorText, type EditionOption } from "./ui";

const TRANSPORT_MODES: [string, string][] = [
  ["sea", "Maritime"],
  ["air", "Aérien"],
  ["road", "Routier"],
  ["rail", "Ferroviaire"],
  ["multimodal", "Multimodal"],
];

const PRIORITIES: [string, string][] = [
  ["normal", "Normale"],
  ["high", "Haute"],
  ["urgent", "Urgente"],
];

/** Points d'entrée proposés ; la saisie reste libre. */
const ENTRY_OFFICES = ["Port d'Owendo (Gabon)", "Port-Gentil (Gabon)", "Aéroport Léon-Mba, Libreville (Gabon)"];

/** Pays fréquents dans les dossiers CEMAC, codes ISO 3166 alpha-2. */
const COUNTRIES: [string, string][] = [
  ["CN", "Chine"], ["FR", "France"], ["CM", "Cameroun"], ["CG", "Congo"], ["GA", "Gabon"], ["GQ", "Guinée équatoriale"],
  ["CF", "République centrafricaine"], ["TD", "Tchad"], ["DE", "Allemagne"], ["BE", "Belgique"], ["ES", "Espagne"],
  ["IT", "Italie"], ["NL", "Pays-Bas"], ["GB", "Royaume-Uni"], ["US", "États-Unis"], ["IN", "Inde"], ["JP", "Japon"],
  ["KR", "Corée du Sud"], ["TR", "Turquie"], ["AE", "Émirats arabes unis"], ["ZA", "Afrique du Sud"], ["NG", "Nigeria"],
  ["MA", "Maroc"], ["BR", "Brésil"],
];

const USAGES: [string, string][] = [
  ["invoice", "Facture"],
  ["transport", "Document de transport"],
  ["packing_list", "Liste de colisage"],
  ["origin", "Certificat d'origine"],
  ["other", "Autre pièce"],
];

const flag = (code: string) =>
  code.length === 2 ? String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65)) : "";
const countryName = (code: string) => COUNTRIES.find(([c]) => c === code)?.[1] ?? code;
const label = (list: [string, string][], value: string) => list.find(([v]) => v === value)?.[1] ?? "";

/** Rôle probable d'une pièce d'après son nom ; l'utilisateur le corrige avant création. */
export function guessUsage(name: string): string {
  const n = name.toLowerCase();
  if (/pack|colis/.test(n)) return "packing_list";
  if (/(^|[^a-z])(bl|b-l|awb|lta|cmr)([^a-z]|$)|connaiss|lading/.test(n)) return "transport";
  if (/origin|(^|[^a-z])co([^a-z]|$)/.test(n)) return "origin";
  if (/inv|fact/.test(n)) return "invoice";
  return "other";
}

function formatBytes(n: number) {
  return n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} Ko` : `${(n / 1024 / 1024).toFixed(1).replace(".", ",")} Mo`;
}

function Field({ label: text, required, icon, children, wide }: { label: string; required?: boolean; icon?: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <label className={`nc-field${wide ? " nc-wide" : ""}`}>
      <span className="nc-label">
        {text}
        {required && <span className="nc-req" aria-hidden="true"> *</span>}
      </span>
      <span className={`nc-control${icon ? " nc-has-icon" : ""}`}>
        {icon && <span className="nc-icon">{icon}</span>}
        {children}
      </span>
    </label>
  );
}

function FileGlyph({ usage }: { usage: string }) {
  const tone = usage === "transport" ? "blue" : usage === "origin" ? "green" : usage === "invoice" ? "red" : "gray";
  return (
    <svg className={`doc-glyph doc-glyph-${tone}`} viewBox="0 0 26 32" width={20} height={25} aria-hidden="true">
      <path d="M3 0h14l9 9v20a3 3 0 0 1-3 3H3a3 3 0 0 1-3-3V3a3 3 0 0 1 3-3z" fill="currentColor" />
      <path d="M17 0v6a3 3 0 0 0 3 3h6z" fill="#fff" fillOpacity=".45" />
      <path d="M7.5 15h11M7.5 19h11M7.5 23h7" stroke="#fff" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}

function SummaryRow({ icon, name, children }: { icon: IconName; name: string; children: ReactNode }) {
  return (
    <div>
      <dt><Icon name={icon} size={17} /> {name}</dt>
      <dd>{children}</dd>
    </div>
  );
}

type Pending = { key: string; file: File; usage: string };

export function NewCasePage({ membership, me }: { membership: Membership; me: Pick<Me, "id" | "full_name" | "email"> }) {
  const [importers, setImporters] = useState<Importer[]>([]);
  const [editions, setEditions] = useState<EditionOption[]>([]);
  const [form, setForm] = useState({
    importer_id: "",
    client_reference: "",
    transport_mode: "",
    entry_office: "",
    origin_country: "",
    provenance_country: "",
    assigned_to_id: me.id,
    priority: "normal",
    target_edition_id: "",
  });
  const [files, setFiles] = useState<Pending[]>([]);
  const [menu, setMenu] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const formRef = useRef<HTMLDivElement>(null);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  useEffect(() => {
    api.importers().then((p) => setImporters(p.results), () => setImporters([]));
    api.editions().then(
      (list) => {
        const usable = list.filter((e) => e.publication_state !== "withdrawn");
        setEditions(usable);
        // Le tarif en service est choisi par défaut ; il reste modifiable dans le dossier.
        const preferred = usable.find((e) => e.publication_state === "operational") ?? usable[0];
        if (preferred) setForm((f) => (f.target_edition_id ? f : { ...f, target_edition_id: preferred.id }));
      },
      () => setEditions([]),
    );
  }, []);

  if (!canEditCases(membership)) {
    return <p className="empty">Votre rôle ne permet pas de créer un dossier.</p>;
  }

  const importer = importers.find((i) => i.id === form.importer_id) ?? null;
  const nif = importer?.identifiers?.nif ?? importer?.identifiers?.NIF ?? "";
  const myName = `${me.full_name || me.email} (Moi)`;

  function addFiles(list: FileList | null) {
    if (!list) return;
    // La liste est copiée tout de suite : le champ fichier est vidé juste après.
    const added = [...list].map((file) => ({ key: crypto.randomUUID(), file, usage: guessUsage(file.name) }));
    setFiles((prev) => [...prev, ...added]);
  }

  const done = [
    Boolean(form.importer_id),
    Boolean(form.transport_mode && form.entry_office),
    files.length > 0,
  ];
  const current = done.indexOf(false) === -1 ? 3 : done.indexOf(false);
  const STEPS = ["Informations du client", "Type d'importation", "Documents initiaux", "Confirmation"];

  async function create(read: boolean) {
    setError(null);
    try {
      setBusy("Création du dossier…");
      const data = Object.fromEntries(Object.entries(form).filter(([, v]) => v));
      const created = await api.createCase(data);
      let readLink: string | null = null;
      for (const [i, p] of files.entries()) {
        setBusy(`Envoi des pièces (${i + 1}/${files.length})…`);
        let link;
        try {
          link = await api.uploadDocument(created.id, p.file, p.usage, "", crypto.randomUUID());
        } catch (err) {
          if (!(err instanceof ApiError && err.code === "DUPLICATE_DOCUMENT")) throw err;
          // Fichier déjà connu de la société : on rattache la pièce existante, sans nouveau dépôt.
          const existing = (err.details.existing as { id: string }[] | undefined)?.[0];
          if (!existing) throw err;
          link = await api.reuseDocument(created.id, existing.id, p.usage);
        }
        if (read && !readLink && p.usage === "invoice" && link.document.readability === "ok") {
          readLink = link.id;
          setBusy("Lancement de la lecture…");
          await api.extract(link.id, { ocr: link.document.mime.startsWith("image/") }).catch(() => undefined);
        }
      }
      navigate(`/dossiers/${created.id}/${read ? "documents" : "apercu"}`);
    } catch (err) {
      setError(errorText(err, "Création impossible."));
      setBusy(null);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void create(true);
  }

  const countryOptions = (
    <>
      <option value="">À renseigner</option>
      {COUNTRIES.map(([code, name]) => (
        <option key={code} value={code}>{flag(code)}  {name}</option>
      ))}
    </>
  );

  return (
    <div className="nc">
      <nav className="breadcrumb nc-breadcrumb" aria-label="Fil d’Ariane">
        <button type="button" className="link" onClick={() => navigate("/dossiers")}>
          <Icon name="chevronLeft" size={13} /> Mes dossiers
        </button>
        <Icon name="chevronRight" size={14} />
        <span>Nouveau dossier</span>
      </nav>
      <h1 className="nc-title">Nouveau dossier</h1>
      <p className="nc-subtitle">Créez un nouveau dossier d’importation avec l’assistance de ClairTransit</p>

      <form className="nc-shell" onSubmit={submit} aria-label="Nouveau dossier">
        <div className="nc-main">
          <ol className="nc-steps" aria-label="Étapes de création du dossier">
            {STEPS.map((s, i) => (
              <li key={s} className={i < current ? "done" : i === current ? "current" : ""} aria-current={i === current ? "step" : undefined}>
                <span className="nc-dot">{i + 1}</span>
                <strong>{s}</strong>
              </li>
            ))}
          </ol>

          <section className="card nc-card" ref={formRef}>
            <h2 className="nc-h2">1. Informations du client</h2>
            <p className="nc-hint">Renseignez les informations générales du dossier et de l’importateur.</p>
            <div className="nc-grid">
              <div className="nc-stack">
                <Field label="Importateur / Client" required icon={<Icon name="search" size={18} />}>
                  <select value={form.importer_id} onChange={set("importer_id")} aria-label="Importateur / Client">
                    <option value="">À renseigner plus tard</option>
                    {importers.map((i) => (
                      <option key={i.id} value={i.id}>{i.name}</option>
                    ))}
                  </select>
                </Field>
                {importer && (
                  <p className="nc-importer">
                    <Icon name="calculator" size={15} />
                    <span>NIF : {nif || "non renseigné"}</span>
                    {importer.address && <><i />{importer.address.split("\n").slice(-1)[0]}</>}
                  </p>
                )}
              </div>
              <Field label="NIF / Référence client" required>
                <input value={form.client_reference} onChange={set("client_reference")} placeholder={nif || "ex. 1234567890"} maxLength={60} />
              </Field>
              <Field label="Type d’opération" required icon={<Icon name="refresh" size={18} />}>
                <select value="import" aria-label="Type d’opération" onChange={() => undefined}>
                  <option value="import">Importation</option>
                </select>
              </Field>
              <Field label="Mode de transport" required icon={<Icon name="ship" size={18} />}>
                <select value={form.transport_mode} onChange={set("transport_mode")}>
                  <option value="">À renseigner</option>
                  {TRANSPORT_MODES.map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </Field>
              <Field label="Port / Bureau d’entrée" required icon={<Icon name="mapPin" size={18} />}>
                <input list="nc-offices" value={form.entry_office} onChange={set("entry_office")} placeholder="ex. Port d'Owendo (Gabon)" maxLength={120} />
                <datalist id="nc-offices">
                  {ENTRY_OFFICES.map((o) => <option key={o} value={o} />)}
                </datalist>
              </Field>
              <Field label="Pays d’origine" required icon={<Icon name="globe" size={18} />}>
                <select value={form.origin_country} onChange={set("origin_country")}>{countryOptions}</select>
              </Field>
              <Field label="Pays de provenance" icon={<Icon name="globe" size={18} />}>
                <select value={form.provenance_country} onChange={set("provenance_country")}>{countryOptions}</select>
              </Field>
              <Field label="Agent responsable" required icon={<Icon name="user" size={18} />}>
                <select value={form.assigned_to_id} onChange={set("assigned_to_id")}>
                  <option value={me.id}>{myName}</option>
                  <option value="">Non affecté</option>
                </select>
              </Field>
              <Field label="Priorité" icon={<Icon name="flag" size={18} />}>
                <select value={form.priority} onChange={set("priority")}>
                  {PRIORITIES.map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </Field>
            </div>

            <div className="nc-docs">
              <div>
                <h2 className="nc-h2">3. Documents initiaux</h2>
                <p className="nc-hint">Ajoutez les documents principaux pour faciliter le traitement du dossier.</p>
                <label
                  className={`nc-drop${drag ? " over" : ""}`}
                  onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
                >
                  <Icon name="cloudUpload" size={40} />
                  <strong>Glissez-déposez vos documents ici</strong>
                  <span>ou cliquez pour parcourir vos fichiers</span>
                  <small>Formats acceptés : PDF, JPG, PNG, Excel</small>
                  <input type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.xlsx" aria-label="Documents initiaux" onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
                </label>
              </div>
              <div className="nc-added">
                <h3>Documents ajoutés <span>({files.length})</span></h3>
                {files.length === 0 ? (
                  <p className="nc-none">Aucun document pour l’instant. Les pièces peuvent aussi être ajoutées après création.</p>
                ) : (
                  <ul>
                    {files.map((p) => (
                      <li key={p.key}>
                        <FileGlyph usage={p.usage} />
                        <span className="nc-file">
                          <strong title={p.file.name}>{p.file.name}</strong>
                          <small>{label(USAGES, p.usage)} • {formatBytes(p.file.size)}</small>
                        </span>
                        <Icon name="checkCircle" size={20} className="nc-ok" />
                        <span className="menu-wrap">
                          <button type="button" className="kebab" aria-label={`Options ${p.file.name}`} onClick={() => setMenu(menu === p.key ? null : p.key)}>
                            <Icon name="more" size={18} />
                          </button>
                          {menu === p.key && (
                            <ul className="menu menu-right" role="menu">
                              {USAGES.map(([v, l]) => (
                                <li key={v} role="menuitem">
                                  <button type="button" onClick={() => { setFiles(files.map((f) => (f.key === p.key ? { ...f, usage: v } : f))); setMenu(null); }}>
                                    {v === p.usage ? <Icon name="check" size={15} /> : <span className="nc-menu-pad" />} {l}
                                  </button>
                                </li>
                              ))}
                              <li role="menuitem">
                                <button type="button" onClick={() => { setFiles(files.filter((f) => f.key !== p.key)); setMenu(null); }}>
                                  <Icon name="x" size={15} /> Retirer
                                </button>
                              </li>
                            </ul>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            {editions.length > 1 && (
              <p className="nc-edition">
                Tarif utilisé :{" "}
                <select value={form.target_edition_id} onChange={set("target_edition_id")} aria-label="Tarif utilisé">
                  {editions.map((e) => (
                    <option key={e.id} value={e.id}>{e.label}</option>
                  ))}
                </select>
              </p>
            )}
            {error && <p role="alert" className="error">⚠ {error}</p>}
          </section>
        </div>

        <aside className="card nc-side" aria-label="Résumé du dossier">
          <div className="nc-side-head">
            <h2>Résumé du dossier</h2>
            <button type="button" className="nc-edit" onClick={() => formRef.current?.querySelector("select")?.focus()}>
              <Icon name="edit" size={16} /> Éditer
            </button>
          </div>
          <dl className="nc-summary">
            <SummaryRow icon="calculator" name="Importateur / Client">{importer?.name ?? <em>À renseigner</em>}</SummaryRow>
            <SummaryRow icon="calculator" name="NIF / Référence">{form.client_reference || nif || <em>À renseigner</em>}</SummaryRow>
            <SummaryRow icon="refresh" name="Type d’opération">Importation</SummaryRow>
            <SummaryRow icon="ship" name="Mode de transport">{label(TRANSPORT_MODES, form.transport_mode) || <em>À renseigner</em>}</SummaryRow>
            <SummaryRow icon="mapPin" name="Port / Bureau">{form.entry_office || <em>À renseigner</em>}</SummaryRow>
            <SummaryRow icon="globe" name="Pays d’origine">
              {form.origin_country ? <><span className="nc-flag">{flag(form.origin_country)}</span> {countryName(form.origin_country)}</> : <em>À renseigner</em>}
            </SummaryRow>
            <SummaryRow icon="globe" name="Pays de provenance">
              {form.provenance_country ? <><span className="nc-flag">{flag(form.provenance_country)}</span> {countryName(form.provenance_country)}</> : <em>À renseigner</em>}
            </SummaryRow>
            <SummaryRow icon="user" name="Agent responsable">{form.assigned_to_id ? me.full_name || me.email : <em>Non affecté</em>}</SummaryRow>
            <SummaryRow icon="flag" name="Priorité">
              <span className={`nc-priority nc-priority-${form.priority}`}>{label(PRIORITIES, form.priority)}</span>
            </SummaryRow>
          </dl>

          <section className="nc-side-docs">
            <div className="nc-side-head">
              <h3>Documents initiaux</h3>
              <span className="chip chip-green">{files.length} fichier{files.length > 1 ? "s" : ""}</span>
            </div>
            {files.length > 0 && (
              <ul>
                {files.map((p) => (
                  <li key={p.key}>
                    <FileGlyph usage={p.usage} />
                    <span title={p.file.name}>{p.file.name}</span>
                    <em>{label(USAGES, p.usage)}</em>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <p className="nc-note">
            <Icon name="info" size={20} />
            Vous pourrez ajouter d’autres documents après la création du dossier.
          </p>
          <div className="nc-actions">
            <button type="button" className="btn-secondary" disabled={busy !== null} onClick={() => void create(false)}>
              <Icon name="save" size={17} /> Enregistrer en brouillon
            </button>
            <button type="submit" className="btn-primary" disabled={busy !== null}>
              {busy ?? <><Icon name="arrowRight" size={18} /> Créer le dossier</>}
            </button>
          </div>
        </aside>
      </form>
    </div>
  );
}
