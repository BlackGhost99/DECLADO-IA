import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, type AntivirusSelfTest, type Supervision as Data, type SupervisionEvent } from "./api";
import { Icon } from "./Icon";
import { tr, type MessageKey } from "./i18n";
import { Chip, PageHeader, StatCard, errorText, relativeTime, type Tone } from "./ui";

type Tab = "antivirus" | "reading" | "ai" | "rejections" | "incidents" | "companies";
type Days = 1 | 7 | 30;

const TABS: { id: Tab; label: MessageKey; icon: "shield" | "file" | "layers" | "alert" | "x" | "users" }[] = [
  { id: "antivirus", label: "sup.tabAntivirus", icon: "shield" },
  { id: "reading", label: "sup.tabReading", icon: "file" },
  { id: "ai", label: "sup.tabAI", icon: "layers" },
  { id: "rejections", label: "sup.tabRejections", icon: "x" },
  { id: "incidents", label: "sup.tabIncidents", icon: "alert" },
  { id: "companies", label: "sup.tabCompanies", icon: "users" },
];

const LEVEL_TONE: Record<SupervisionEvent["level"], Tone> = { info: "blue", warning: "amber", error: "red" };
const when = (iso: string) => new Date(iso).toLocaleString();
const num = (n: number | null | undefined) => (n === null || n === undefined ? "—" : n.toLocaleString());

/** Console > Supervision : l'exploitant voit si la plateforme fonctionne, jamais le contenu des pièces. */
export function Supervision() {
  const [days, setDays] = useState<Days>(7);
  const [tab, setTab] = useState<Tab>("antivirus");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    api.supervision(days).then(
      (d) => { setData(d); setLoading(false); },
      (err) => { setError(errorText(err, tr("sup.loadError"))); setLoading(false); },
    );
  }, [days]);
  useEffect(load, [load]);

  return (
    <>
      <PageHeader title={tr("sup.title")} subtitle={tr("sup.subtitle")}>
        <label className="inline">
          <span className="visually-hidden">{tr("sup.period")}</span>
          <select aria-label={tr("sup.period")} value={days} onChange={(e) => setDays(Number(e.target.value) as Days)}>
            <option value={1}>{tr("sup.days1")}</option>
            <option value={7}>{tr("sup.days7")}</option>
            <option value={30}>{tr("sup.days30")}</option>
          </select>
        </label>
        <button type="button" className="btn-secondary" onClick={load} disabled={loading}>
          <Icon name="refresh" size={18} /> {tr("sup.refresh")}
        </button>
      </PageHeader>
      {error && <p role="alert" className="error">⚠ {error}</p>}
      {!data ? (
        !error && <p className="muted">{tr("loading")}</p>
      ) : (
        <>
          <Overview data={data} />
          <div role="tablist" className="tabs" aria-label={tr("sup.sections")}>
            {TABS.map((t) => (
              <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>
                <Icon name={t.icon} size={18} /> {tr(t.label)}
              </button>
            ))}
          </div>
          {tab === "antivirus" && <AntivirusTab data={data} onTested={load} />}
          {tab === "reading" && <ReadingTab data={data} />}
          {tab === "ai" && <AITab data={data} />}
          {tab === "rejections" && <EventsCard title={tr("sup.rejectionsTitle")} help={tr("sup.rejectionsHelp")} items={data.rejections} />}
          {tab === "incidents" && <IncidentsTab data={data} />}
          {tab === "companies" && <CompaniesTab data={data} />}
          <p className="muted small">{tr("sup.generated", { when: when(data.generated_at) })} · {tr("sup.privacy")}</p>
        </>
      )}
    </>
  );
}

function Overview({ data }: { data: Data }) {
  const av = data.antivirus;
  const ocr = data.reading.engines.ocr;
  const provider = data.ai.provider;
  return (
    <div className="stats" aria-label={tr("sup.overview")}>
      <StatCard icon="shield" tone={av.probe.state === "ok" ? "green" : "red"} label={tr("sup.antivirus")}
        value={tr(av.probe.state === "ok" ? "sup.avOk" : "sup.avDown")}
        hint={tr("sup.scanned", { n: av.counts.clean, refused: av.counts.malware })} />
      <StatCard icon="file" tone={data.reading.counts.failed ? "amber" : "green"} label={tr("sup.readings")}
        value={num(data.reading.counts.total)}
        hint={tr("sup.readingsHint", { ok: data.reading.counts.succeeded, failed: data.reading.counts.failed })} />
      <StatCard icon="eye" tone={ocr.available ? "green" : "gray"} label={tr("sup.ocr")}
        value={tr(ocr.available ? "sup.available" : "sup.unavailable")}
        hint={ocr.available ? `Tesseract ${ocr.version}` : tr("sup.ocrHint")} />
      <StatCard icon="layers" tone={provider.configured ? "green" : "gray"} label={tr("sup.ai")}
        value={provider.configured ? provider.label ?? "—" : tr("sup.aiOff")}
        hint={tr("sup.aiHint", { n: data.ai.counts.sent ?? 0 })} />
      <StatCard icon="alert" tone={data.incidents.server_errors ? "red" : data.rejections.length ? "amber" : "green"}
        label={tr("sup.problems")} value={num(data.incidents.server_errors + data.incidents.refused_actions + data.rejections.length)}
        hint={tr("sup.problemsHint", { errors: data.incidents.server_errors, rejected: data.rejections.length })} />
    </div>
  );
}

function AntivirusTab({ data, onTested }: { data: Data; onTested: () => void }) {
  const av = data.antivirus;
  const [test, setTest] = useState<AntivirusSelfTest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run() {
    setBusy(true); setError("");
    try {
      setTest(await api.antivirusSelfTest());
      onTested();
    } catch (err) { setError(errorText(err, tr("sup.loadError"))); }
    finally { setBusy(false); }
  }
  return (
    <div className="grid-2-1">
      <section className="card" aria-labelledby="sup-av-title">
        <h2 id="sup-av-title" className="card-title">{tr("sup.avTitle")}</h2>
        <dl className="ia-kv">
          <dt>{tr("sup.state")}</dt>
          <dd><Chip tone={av.probe.state === "ok" ? "green" : "red"}>{tr(av.probe.state === "ok" ? "sup.avOk" : "sup.avDown")}</Chip></dd>
          {av.probe.state === "ok" ? (
            <>
              <dt>{tr("sup.engine")}</dt><dd>{av.probe.engine}</dd>
              <dt>{tr("sup.signatures")}</dt><dd>{av.probe.signatures} · {av.probe.signatures_date}</dd>
              <dt>{tr("sup.response")}</dt><dd>{tr("sup.ms", { n: av.probe.response_ms ?? 0 })}</dd>
            </>
          ) : (
            <><dt>{tr("sup.reason")}</dt><dd>{av.probe.message}</dd></>
          )}
          <dt>{tr("sup.mode")}</dt><dd>{tr("sup.failClosed")}</dd>
          <dt>{tr("sup.cleanCount")}</dt><dd>{num(av.counts.clean)}</dd>
          <dt>{tr("sup.malwareCount")}</dt><dd>{num(av.counts.malware)}</dd>
          <dt>{tr("sup.unavailableCount")}</dt><dd>{num(av.counts.unavailable)}</dd>
          <dt>{tr("sup.lastClean")}</dt><dd>{av.last_clean_at ? relativeTime(av.last_clean_at) : "—"}</dd>
          <dt>{tr("sup.lastTest")}</dt>
          <dd>{av.last_test ? <><Chip tone={LEVEL_TONE[av.last_test.level]}>{tr(av.last_test.code === "SELF_TEST_PASSED" ? "sup.testOk" : "sup.testFailed")}</Chip> {relativeTime(av.last_test.at)}{av.last_test.actor ? ` · ${av.last_test.actor}` : ""}</> : tr("sup.never")}</dd>
        </dl>
        <p className="note-blue small">{tr("sup.avNote")}</p>
      </section>
      <section className="card" aria-labelledby="sup-test-title">
        <h2 id="sup-test-title" className="card-title">{tr("sup.testTitle")}</h2>
        <p className="muted small">{tr("sup.testHelp")}</p>
        <button type="button" className="btn-primary" onClick={() => void run()} disabled={busy}>
          <Icon name="shield" size={18} /> {tr(busy ? "sup.testing" : "sup.runTest")}
        </button>
        {error && <p role="alert" className="error">{error}</p>}
        {test && (
          <ul className="small" aria-live="polite">
            {test.steps.map((s) => (
              <li key={s.step}><Chip tone={s.ok ? "green" : "red"}>{tr(s.ok ? "sup.ok" : "sup.ko")}</Chip> {s.message}</li>
            ))}
          </ul>
        )}
      </section>
      <EventsCard title={tr("sup.avEvents")} help={tr("sup.avEventsHelp")} items={av.events} />
    </div>
  );
}

function ReadingTab({ data }: { data: Data }) {
  const r = data.reading;
  return (
    <>
      <div className="grid-2-1">
        <section className="card" aria-labelledby="sup-engines-title">
          <h2 id="sup-engines-title" className="card-title">{tr("sup.enginesTitle")}</h2>
          <p className="muted small">{tr("sup.enginesHelp")}</p>
          <dl className="ia-kv">
            <dt>{tr("sup.pdfText")}</dt><dd><Chip tone="green">{tr("sup.available")}</Chip></dd>
            <dt>{tr("sup.xlsx")}</dt><dd><Chip tone="green">{tr("sup.available")}</Chip></dd>
            <dt>{tr("sup.ocr")}</dt>
            <dd>
              <Chip tone={r.engines.ocr.available ? "green" : "gray"}>{tr(r.engines.ocr.available ? "sup.available" : "sup.unavailable")}</Chip>
              {r.engines.ocr.available && ` Tesseract ${r.engines.ocr.version} · ${tr("sup.languages", { list: r.engines.ocr.languages.join(", ") || "—" })}`}
            </dd>
            <dt>{tr("sup.ai")}</dt>
            <dd>{r.engines.ai.configured ? `${r.engines.ai.label ?? ""} · ${r.engines.ai.model ?? ""}` : tr("sup.aiOff")}</dd>
            <dt>{tr("sup.average")}</dt><dd>{r.counts.average_seconds === null ? "—" : tr("sup.seconds", { n: r.counts.average_seconds })}</dd>
            <dt>{tr("sup.running")}</dt><dd>{num(r.counts.running)}</dd>
          </dl>
        </section>
        <section className="card" aria-labelledby="sup-by-title">
          <h2 id="sup-by-title" className="card-title">{tr("sup.byReader")}</h2>
          <Table head={[tr("sup.pieceType"), tr("sup.count"), tr("sup.failed")]}
            rows={r.by_reader.map((x) => [x.label, num(x.count), num(x.failed)])} empty={tr("sup.none")} />
          <h3 className="card-title">{tr("sup.byParser")}</h3>
          <Table head={[tr("sup.engine"), tr("sup.count")]} rows={r.by_parser.map((x) => [x.label, num(x.count)])} empty={tr("sup.none")} />
        </section>
      </div>
      <section className="card" aria-labelledby="sup-fail-title">
        <h2 id="sup-fail-title" className="card-title">{tr("sup.readingFailures")}</h2>
        <Table
          head={[tr("sup.when"), tr("sup.company"), tr("sup.case"), tr("sup.pieceType"), tr("sup.engine"), tr("sup.error")]}
          rows={r.failures.map((f) => [when(f.at), f.organization ?? "—", f.case_reference, f.reader, f.parser,
            <><code>{f.error_code}</code> {f.error_message}{f.attempt > 1 ? ` (${tr("sup.attempt", { n: f.attempt })})` : ""}</>])}
          empty={tr("sup.noFailure")}
        />
      </section>
    </>
  );
}

function AITab({ data }: { data: Data }) {
  const a = data.ai;
  return (
    <>
      <div className="grid-2-1">
        <section className="card" aria-labelledby="sup-ai-title">
          <h2 id="sup-ai-title" className="card-title">{tr("sup.aiTitle")}</h2>
          <dl className="ia-kv">
            <dt>{tr("sup.provider")}</dt><dd>{a.provider.label ?? tr("sup.aiOff")}{a.provider.free_tier ? ` · ${tr("sup.freeTier")}` : ""}</dd>
            <dt>{tr("sup.model")}</dt><dd>{a.provider.model ?? "—"}</dd>
            <dt>{tr("sup.key")}</dt><dd><Chip tone={a.provider.configured ? "green" : "gray"}>{tr(a.provider.configured ? "sup.keyOk" : "sup.keyMissing")}</Chip></dd>
            <dt>{tr("sup.companiesOn")}</dt><dd>{num(a.organizations_enabled)}</dd>
            {Object.entries(a.counts).map(([status, n]) => (
              <span key={status} style={{ display: "contents" }}><dt>{a.status_labels[status] ?? status}</dt><dd>{num(n)}</dd></span>
            ))}
            <dt>{tr("sup.tokens")}</dt><dd>{num(a.totals.input_tokens)} / {num(a.totals.output_tokens)}</dd>
            <dt>{tr("sup.cost")}</dt><dd>{a.totals.cost_estimate === null ? tr("sup.unknown") : `${a.totals.cost_estimate} $`}</dd>
            <dt>{tr("sup.latency")}</dt><dd>{a.totals.average_latency_ms === null ? "—" : tr("sup.ms", { n: a.totals.average_latency_ms })}</dd>
            <dt>{tr("sup.sentChars")}</dt><dd>{num(a.totals.sent_chars)}</dd>
          </dl>
          <p className="note-blue small">{tr("sup.aiNote")}</p>
        </section>
        <section className="card" aria-labelledby="sup-fields-title">
          <h2 id="sup-fields-title" className="card-title">{tr("sup.aiFields")}</h2>
          <p className="muted small">{tr("sup.aiFieldsHelp")}</p>
          <Table head={[tr("sup.field"), tr("sup.asked"), tr("sup.kept"), tr("sup.discarded")]}
            rows={a.fields.map((f) => [f.field, num(f.requested), num(f.found), num(f.rejected)])} empty={tr("sup.none")} />
        </section>
      </div>
      <section className="card" aria-labelledby="sup-ai-recent">
        <h2 id="sup-ai-recent" className="card-title">{tr("sup.aiRecent")}</h2>
        <Table
          head={[tr("sup.when"), tr("sup.company"), tr("sup.state"), tr("sup.provider"), tr("sup.asked"), tr("sup.kept"), tr("sup.discarded")]}
          rows={a.recent.map((x) => [
            when(x.at), x.organization ?? "—",
            <>{x.status_label}{x.error_code ? <> · <code>{x.error_code}</code> {x.error_message}</> : null}</>,
            x.provider ? `${x.provider} · ${x.model}` : "—",
            x.requested.join(", ") || "—", x.found.join(", ") || "—",
            x.rejected.map((r) => `${r.field} (${r.reason})`).join(", ") || "—",
          ])}
          empty={tr("sup.none")}
        />
      </section>
    </>
  );
}

function IncidentsTab({ data }: { data: Data }) {
  const i = data.incidents;
  return (
    <>
      <EventsCard title={tr("sup.incidentsTitle")} help={tr("sup.incidentsHelp")} items={i.events} />
      <section className="card" aria-labelledby="sup-jobs-title">
        <h2 id="sup-jobs-title" className="card-title">{tr("sup.jobsTitle")}</h2>
        <Table head={[tr("sup.when"), tr("sup.company"), tr("sup.job"), tr("sup.error")]}
          rows={i.failed_jobs.map((j) => [when(j.at), j.organization ?? "—", `${j.kind}${j.phase ? ` · ${j.phase}` : ""}`,
            <><code>{j.error_code}</code> {j.error_message}</>])}
          empty={tr("sup.noFailure")} />
      </section>
    </>
  );
}

function CompaniesTab({ data }: { data: Data }) {
  return (
    <section className="card" aria-labelledby="sup-org-title">
      <h2 id="sup-org-title" className="card-title">{tr("sup.companiesTitle")}</h2>
      <p className="muted small">{tr("sup.companiesHelp")}</p>
      <Table
        head={[tr("sup.company"), tr("sup.cases"), tr("sup.documents"), tr("sup.readingsOk"), tr("sup.failed"),
          tr("sup.rejected"), tr("sup.errors"), tr("sup.aiSent"), tr("sup.lastActivity")]}
        rows={data.organizations.map((o) => [
          <>{o.name}{o.is_demo ? <> <Chip tone="gray">{tr("demo")}</Chip></> : null}</>,
          num(o.cases), num(o.documents), num(o.readings),
          o.reading_failures ? <Chip tone="amber">{o.reading_failures}</Chip> : "0",
          o.rejected_documents ? <Chip tone="amber">{o.rejected_documents}</Chip> : "0",
          o.errors ? <Chip tone="red">{o.errors}</Chip> : "0",
          num(o.ai_sent), o.last_activity ? relativeTime(o.last_activity) : "—",
        ])}
        empty={tr("sup.none")}
      />
    </section>
  );
}

const DETAIL_KEYS: [string, MessageKey][] = [
  ["extension", "sup.dExtension"], ["declared_mime", "sup.dMime"], ["bytes", "sup.dBytes"], ["sha256_prefix", "sup.dHash"],
  ["method", "sup.dMethod"], ["route", "sup.dRoute"], ["http_status", "sup.dStatus"], ["context", "sup.dContext"],
];

function details(e: SupervisionEvent): string {
  const parts = DETAIL_KEYS.filter(([k]) => e.details[k] !== undefined && e.details[k] !== "" && e.details[k] !== null)
    .map(([k, label]) => `${tr(label)} : ${String(e.details[k])}`);
  const steps = e.details.steps as { ok: boolean; message: string }[] | undefined;
  if (steps) parts.push(...steps.map((s) => `${s.ok ? "✓" : "✗"} ${s.message}`));
  return parts.join(" · ");
}

function EventsCard({ title, help, items }: { title: string; help: string; items: SupervisionEvent[] }) {
  return (
    <section className="card" aria-label={title}>
      <h2 className="card-title">{title}</h2>
      <p className="muted small">{help}</p>
      <Table
        head={[tr("sup.when"), tr("sup.company"), tr("sup.who"), tr("sup.what"), tr("sup.details")]}
        rows={items.map((e) => [
          when(e.at), e.organization ?? "—", e.actor ?? "—",
          <><Chip tone={LEVEL_TONE[e.level]}>{e.code}</Chip> {e.message}</>,
          <span className="small">{details(e)}{e.request_id ? ` · ${tr("sup.dRequest")} ${e.request_id.slice(0, 8)}` : ""}</span>,
        ])}
        empty={tr("sup.nothing")}
      />
    </section>
  );
}

function Table({ head, rows, empty }: { head: string[]; rows: ReactNode[][]; empty: string }) {
  if (rows.length === 0) return <p className="empty">{empty}</p>;
  return (
    <div className="table-wrap">
      <table className="data">
        <thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}
