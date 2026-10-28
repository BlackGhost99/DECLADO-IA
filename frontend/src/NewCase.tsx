// Écran « Nouveau dossier » : formulaire en sections, résumé à droite, pièces initiales jointes à la création.
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api, ApiError, type Importer, type Me, type Membership } from "./api";
import { canEditCases } from "./Cases";
import { readerOf } from "./pieceTypes";
import { Icon, type IconName } from "./Icon";
import { navigate } from "./router";
import { tr, type MessageKey } from "./i18n";
import { errorText, localeTag, type EditionOption } from "./ui";

const TRANSPORT_MODES: [string, MessageKey][] = [
  ["sea", "sea"],
  ["air", "air"],
  ["road", "road"],
  ["rail", "rail"],
  ["multimodal", "multimodal"],
];

const PRIORITIES: [string, MessageKey][] = [
  ["normal", "nc.prioNormal"],
  ["high", "nc.prioHigh"],
  ["urgent", "nc.prioUrgent"],
];

/** Points d'entrée proposés ; la saisie reste libre. */
const ENTRY_OFFICES = ["Port d'Owendo (Gabon)", "Port-Gentil (Gabon)", "Aéroport Léon-Mba, Libreville (Gabon)"];

/** Pays fréquents dans les dossiers CEMAC, codes ISO 3166 alpha-2 ; leur nom vient du navigateur, dans la langue affichée. */
const COUNTRIES = ["CN", "FR", "CM", "CG", "GA", "GQ", "CF", "TD", "DE", "BE", "ES", "IT", "NL", "GB", "US", "IN", "JP", "KR", "TR", "AE", "ZA", "NG", "MA", "BR"];

/** « auto » : le type est reconnu d'après le titre de la pièce au dépôt. */
const USAGES: [string, MessageKey][] = [
  ["auto", "usage.autoShort"],
  ["invoice", "invoice"],
  ["transport", "transportDoc"],
  ["insurance", "usage.insurance"],
  ["freight", "usage.freight"],
  ["packing_list", "packing"],
  ["origin", "originCert"],
  ["other", "otherDoc"],
];

const flag = (code: string) =>
  code.length === 2 ? String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65)) : "";
function countryName(code: string) {
  try {
    return new Intl.DisplayNames([localeTag()], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}
function label(list: [string, MessageKey][], value: string) {
  const key = list.find(([v]) => v === value)?.[1];
  return key ? tr(key) : "";
}

/** Rôle probable d'une pièce d'après son nom, pour son icône ; le type retenu vient du titre lu au dépôt. */
export function guessUsage(name: string): string {
  const n = name.toLowerCase();
  if (/pack|colis/.test(n)) return "packing_list";
  if (/(^|[^a-z])(bl|b-l|awb|lta|cmr)([^a-z]|$)|connaiss|lading/.test(n)) return "transport";
  if (/origin|(^|[^a-z])co([^a-z]|$)/.test(n)) return "origin";
  if (/inv|fact/.test(n)) return "invoice";
  return "other";
}

function formatBytes(n: number) {
  return n < 1024 * 1024 ? tr("unit.kb", { n: Math.max(1, Math.round(n / 1024)) }) : tr("unit.mb", { n: (n / 1024 / 1024).toLocaleString(localeTag(), { maximumFractionDigits: 1, minimumFractionDigits: 1 }) });
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
    return <p className="empty">{tr("nc.noRole")}</p>;
  }

  const importer = importers.find((i) => i.id === form.importer_id) ?? null;
  const nif = importer?.identifiers?.nif ?? importer?.identifiers?.NIF ?? "";
  const myName = tr("nc.meSuffix", { name: me.full_name || me.email });

  function addFiles(list: FileList | null) {
    if (!list) return;
    // La liste est copiée tout de suite : le champ fichier est vidé juste après.
    const added = [...list].map((file) => ({ key: crypto.randomUUID(), file, usage: "auto" }));
    setFiles((prev) => [...prev, ...added]);
  }

  const done = [
    Boolean(form.importer_id),
    Boolean(form.transport_mode && form.entry_office),
    files.length > 0,
  ];
  const current = done.indexOf(false) === -1 ? 3 : done.indexOf(false);
  const STEPS = [tr("nc.stepClient"), tr("nc.stepImportType"), tr("nc.stepDocs"), tr("nc.stepConfirm")];

  async function create(read: boolean) {
    setError(null);
    try {
      setBusy(tr("nc.creating"));
      const data = Object.fromEntries(Object.entries(form).filter(([, v]) => v));
      const created = await api.createCase(data);
      for (const [i, p] of files.entries()) {
        setBusy(tr("nc.uploading", { i: i + 1, n: files.length }));
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
        // Chaque pièce qui a une lecture automatique (facture, transport, assurance, fret) est lue.
        if (read && readerOf(link) && link.document.readability === "ok" && !link.latest_extraction) {
          setBusy(tr("nc.startReading"));
          await api.extract(link.id, { ocr: link.document.mime.startsWith("image/") }).catch(() => undefined);
        }
      }
      navigate(`/dossiers/${created.id}/${read ? "documents" : "apercu"}`);
    } catch (err) {
      setError(errorText(err, tr("nc.createFailed")));
      setBusy(null);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void create(true);
  }

  const countryOptions = (
    <>
      <option value="">{tr("nc.toFill")}</option>
      {COUNTRIES.map((code) => (
        <option key={code} value={code}>{flag(code)}  {countryName(code)}</option>
      ))}
    </>
  );

  return (
    <div className="nc">
      <nav className="breadcrumb nc-breadcrumb" aria-label={tr("nav.breadcrumb")}>
        <button type="button" className="link" onClick={() => navigate("/dossiers")}>
          <Icon name="chevronLeft" size={13} /> {tr("nav.myCases")}
        </button>
        <Icon name="chevronRight" size={14} />
        <span>{tr("nav.newCase")}</span>
      </nav>
      <h1 className="nc-title">{tr("nav.newCase")}</h1>
      <p className="nc-subtitle">{tr("nc.subtitle")}</p>

      <form className="nc-shell" onSubmit={submit} aria-label={tr("nav.newCase")}>
        <div className="nc-main">
          <ol className="nc-steps" aria-label={tr("nc.steps")}>
            {STEPS.map((s, i) => (
              <li key={s} className={i < current ? "done" : i === current ? "current" : ""} aria-current={i === current ? "step" : undefined}>
                <span className="nc-dot">{i + 1}</span>
                <strong>{s}</strong>
              </li>
            ))}
          </ol>

          <section className="card nc-card" ref={formRef}>
            <h2 className="nc-h2">{tr("nc.clientTitle")}</h2>
            <p className="nc-hint">{tr("nc.clientHint")}</p>
            <div className="nc-grid">
              <div className="nc-stack">
                <Field label={tr("nc.importerClient")} required icon={<Icon name="search" size={18} />}>
                  <select value={form.importer_id} onChange={set("importer_id")} aria-label={tr("nc.importerClient")}>
                    <option value="">{tr("nc.later")}</option>
                    {importers.map((i) => (
                      <option key={i.id} value={i.id}>{i.name}</option>
                    ))}
                  </select>
                </Field>
                {importer && (
                  <p className="nc-importer">
                    <Icon name="calculator" size={15} />
                    <span>{tr("nc.nif", { nif: nif || tr("nc.notFilled") })}</span>
                    {importer.address && <><i />{importer.address.split("\n").slice(-1)[0]}</>}
                  </p>
                )}
              </div>
              <Field label={tr("nc.nifRef")} required>
                <input value={form.client_reference} onChange={set("client_reference")} placeholder={nif || tr("nc.example", { value: "1234567890" })} maxLength={60} />
              </Field>
              <Field label={tr("nc.operationType")} required icon={<Icon name="refresh" size={18} />}>
                <select value="import" aria-label={tr("nc.operationType")} onChange={() => undefined}>
                  <option value="import">{tr("import")}</option>
                </select>
              </Field>
              <Field label={tr("export.transport")} required icon={<Icon name="ship" size={18} />}>
                <select value={form.transport_mode} onChange={set("transport_mode")}>
                  <option value="">{tr("nc.toFill")}</option>
                  {TRANSPORT_MODES.map(([v, l]) => (
                    <option key={v} value={v}>{tr(l)}</option>
                  ))}
                </select>
              </Field>
              <Field label={tr("nc.entryOffice")} required icon={<Icon name="mapPin" size={18} />}>
                <input list="nc-offices" value={form.entry_office} onChange={set("entry_office")} placeholder={tr("nc.example", { value: ENTRY_OFFICES[0] })} maxLength={120} />
                <datalist id="nc-offices">
                  {ENTRY_OFFICES.map((o) => <option key={o} value={o} />)}
                </datalist>
              </Field>
              <Field label={tr("nc.originCountry")} required icon={<Icon name="globe" size={18} />}>
                <select value={form.origin_country} onChange={set("origin_country")}>{countryOptions}</select>
              </Field>
              <Field label={tr("nc.provenance")} icon={<Icon name="globe" size={18} />}>
                <select value={form.provenance_country} onChange={set("provenance_country")}>{countryOptions}</select>
              </Field>
              <Field label={tr("nc.agent")} required icon={<Icon name="user" size={18} />}>
                <select value={form.assigned_to_id} onChange={set("assigned_to_id")}>
                  <option value={me.id}>{myName}</option>
                  <option value="">{tr("board.unassignedOne")}</option>
                </select>
              </Field>
              <Field label={tr("nc.priority")} icon={<Icon name="flag" size={18} />}>
                <select value={form.priority} onChange={set("priority")}>
                  {PRIORITIES.map(([v, l]) => (
                    <option key={v} value={v}>{tr(l)}</option>
                  ))}
                </select>
              </Field>
            </div>

            <div className="nc-docs">
              <div>
                <h2 className="nc-h2">{tr("nc.docsTitle")}</h2>
                <p className="nc-hint">{tr("nc.docsHint")}</p>
                <label
                  className={`nc-drop${drag ? " over" : ""}`}
                  onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
                >
                  <Icon name="cloudUpload" size={40} />
                  <strong>{tr("nc.drop")}</strong>
                  <span>{tr("nc.browse")}</span>
                  <small>{tr("nc.formats")}</small>
                  <input type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.xlsx" aria-label={tr("nc.stepDocs")} onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
                </label>
              </div>
              <div className="nc-added">
                <h3>{tr("nc.added")} <span>({files.length})</span></h3>
                {files.length === 0 ? (
                  <p className="nc-none">{tr("nc.none")}</p>
                ) : (
                  <ul>
                    {files.map((p) => (
                      <li key={p.key}>
                        <FileGlyph usage={p.usage === "auto" ? guessUsage(p.file.name) : p.usage} />
                        <span className="nc-file">
                          <strong title={p.file.name}>{p.file.name}</strong>
                          <small>{label(USAGES, p.usage)} • {formatBytes(p.file.size)}</small>
                        </span>
                        <Icon name="checkCircle" size={20} className="nc-ok" />
                        <span className="menu-wrap">
                          <button type="button" className="kebab" aria-label={tr("nc.options", { name: p.file.name })} onClick={() => setMenu(menu === p.key ? null : p.key)}>
                            <Icon name="more" size={18} />
                          </button>
                          {menu === p.key && (
                            <ul className="menu menu-right" role="menu">
                              {USAGES.map(([v, l]) => (
                                <li key={v} role="menuitem">
                                  <button type="button" onClick={() => { setFiles(files.map((f) => (f.key === p.key ? { ...f, usage: v } : f))); setMenu(null); }}>
                                    {v === p.usage ? <Icon name="check" size={15} /> : <span className="nc-menu-pad" />} {tr(l)}
                                  </button>
                                </li>
                              ))}
                              <li role="menuitem">
                                <button type="button" onClick={() => { setFiles(files.filter((f) => f.key !== p.key)); setMenu(null); }}>
                                  <Icon name="x" size={15} /> {tr("nc.remove")}
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
                {tr("nc.tariffUsed")} :{" "}
                <select value={form.target_edition_id} onChange={set("target_edition_id")} aria-label={tr("nc.tariffUsed")}>
                  {editions.map((e) => (
                    <option key={e.id} value={e.id}>{e.label}</option>
                  ))}
                </select>
              </p>
            )}
            {error && <p role="alert" className="error">⚠ {error}</p>}
          </section>
        </div>

        <aside className="card nc-side" aria-label={tr("nc.summary")}>
          <div className="nc-side-head">
            <h2>{tr("nc.summary")}</h2>
            <button type="button" className="nc-edit" onClick={() => formRef.current?.querySelector("select")?.focus()}>
              <Icon name="edit" size={16} /> {tr("nc.edit")}
            </button>
          </div>
          <dl className="nc-summary">
            <SummaryRow icon="calculator" name={tr("nc.importerClient")}>{importer?.name ?? <em>{tr("nc.toFill")}</em>}</SummaryRow>
            <SummaryRow icon="calculator" name={tr("nc.nifRefShort")}>{form.client_reference || nif || <em>{tr("nc.toFill")}</em>}</SummaryRow>
            <SummaryRow icon="refresh" name={tr("nc.operationType")}>{tr("import")}</SummaryRow>
            <SummaryRow icon="ship" name={tr("export.transport")}>{label(TRANSPORT_MODES, form.transport_mode) || <em>{tr("nc.toFill")}</em>}</SummaryRow>
            <SummaryRow icon="mapPin" name={tr("nc.portOffice")}>{form.entry_office || <em>{tr("nc.toFill")}</em>}</SummaryRow>
            <SummaryRow icon="globe" name={tr("nc.originCountry")}>
              {form.origin_country ? <><span className="nc-flag">{flag(form.origin_country)}</span> {countryName(form.origin_country)}</> : <em>{tr("nc.toFill")}</em>}
            </SummaryRow>
            <SummaryRow icon="globe" name={tr("nc.provenance")}>
              {form.provenance_country ? <><span className="nc-flag">{flag(form.provenance_country)}</span> {countryName(form.provenance_country)}</> : <em>{tr("nc.toFill")}</em>}
            </SummaryRow>
            <SummaryRow icon="user" name={tr("nc.agent")}>{form.assigned_to_id ? me.full_name || me.email : <em>{tr("board.unassignedOne")}</em>}</SummaryRow>
            <SummaryRow icon="flag" name={tr("nc.priority")}>
              <span className={`nc-priority nc-priority-${form.priority}`}>{label(PRIORITIES, form.priority)}</span>
            </SummaryRow>
          </dl>

          <section className="nc-side-docs">
            <div className="nc-side-head">
              <h3>{tr("nc.stepDocs")}</h3>
              <span className="chip chip-green">{tr("nc.files", { n: files.length })}</span>
            </div>
            {files.length > 0 && (
              <ul>
                {files.map((p) => (
                  <li key={p.key}>
                    <FileGlyph usage={p.usage === "auto" ? guessUsage(p.file.name) : p.usage} />
                    <span title={p.file.name}>{p.file.name}</span>
                    <em>{label(USAGES, p.usage)}</em>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <p className="nc-note">
            <Icon name="info" size={20} />
            {tr("nc.addLater")}
          </p>
          <div className="nc-actions">
            <button type="button" className="btn-secondary" disabled={busy !== null} onClick={() => void create(false)}>
              <Icon name="save" size={17} /> {tr("nc.saveDraft")}
            </button>
            <button type="submit" className="btn-primary" disabled={busy !== null}>
              {busy ?? <><Icon name="arrowRight" size={18} /> {tr("createCase")}</>}
            </button>
          </div>
        </aside>
      </form>
    </div>
  );
}
