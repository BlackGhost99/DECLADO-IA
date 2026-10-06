// Client de l'API ClairTransit : session serveur (cookie HttpOnly) + jeton CSRF.
// Aucun jeton durable n'est stocké dans le navigateur.

export type Role = "declarant" | "validator" | "org_admin";

export interface Membership {
  organization: { id: string; name: string; is_demo: boolean; timezone: string };
  roles: Role[];
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  is_reference_manager: boolean;
  memberships: Membership[];
  active_organization_id: string | null;
}

export interface Importer {
  id: string;
  name: string;
  identifiers: Record<string, string>;
  contacts: Record<string, string>[];
  address: string;
  notes: string;
  row_version: number;
  possible_duplicates?: { id: string; name: string }[];
}

export interface Member {
  id: string;
  email: string;
  full_name: string;
  roles: Role[];
  active: boolean;
  row_version: number;
}

export interface Page<T> {
  count: number;
  results: T[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

const BASE = "/api/v1";

function readCookie(name: string): string | null {
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function ensureCsrf(): Promise<string> {
  let token = readCookie("csrftoken");
  if (!token) {
    await fetch(`${BASE}/auth/csrf`, { credentials: "same-origin" });
    token = readCookie("csrftoken");
  }
  return token ?? "";
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    headers["X-CSRFToken"] = await ensureCsrf();
  }
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return parse<T>(response);
}

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, data.code ?? "ERROR", data.message ?? "Erreur inattendue.", data.details);
  }
  return data as T;
}

export async function upload<T>(path: string, form: FormData, headers: Record<string, string> = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "X-CSRFToken": await ensureCsrf(), ...headers },
    credentials: "same-origin",
    body: form,
  });
  return parse<T>(response);
}

export interface EditionBrief {
  id: string;
  label: string;
  publication_state: "draft" | "consultation" | "operational" | "withdrawn";
}

export interface NodeBrief {
  id: string;
  code: string | null;
  code_display: string;
  kind: string;
  label: string;
  declarable: boolean;
}

export interface SearchResult extends NodeBrief {
  reason: string;
  full_path: string;
  validation_state: string;
  label_damaged: boolean;
  edition: EditionBrief;
}

export interface Evidence {
  record_id: string;
  location: string;
  page_index: number | null;
  printed_page: string;
  cell_range: string;
  line: number | null;
}

export interface Note {
  id: string;
  scope_type: string;
  scope_ref: string;
  heading: string;
  text: string;
  edition: EditionBrief;
  evidence: Evidence | null;
}

export interface NodeDetail extends NodeBrief {
  label_raw: string;
  label_damaged: boolean;
  label_available: boolean;
  validation_state: string;
  full_path: string;
  edition: EditionBrief & {
    warning: string | null;
    source: { title: string; kind_label: string; is_derived_copy: boolean; provenance_note: string };
  };
  ancestors: NodeBrief[];
  children: NodeBrief[];
  evidence: Evidence | null;
  occurrences: (Evidence & { raw_code: string })[];
  rate_observations: {
    warning: string;
    items: { column: string; raw_value: string; value: string | null; quality: string }[];
  };
  notes: Note[];
  related_notes: Note[];
  same_code_in_other_editions: (NodeBrief & { edition: EditionBrief })[];
  issues: { id: string; category: string; severity: string; message: string; state: string }[];
}

export interface RecordDetail extends Evidence {
  source: { title: string; is_derived_copy: boolean; sha256: string };
  header: string[] | null;
  raw_cells: string[];
  raw_text: string;
}

export interface UserBrief {
  id: string;
  email: string;
  full_name: string;
}

export interface Finding {
  code: string;
  severity: string;
  message: string;
  details?: Record<string, unknown> & { subdivisions?: { id: string; code: string; code_display: string; label: string }[] };
}

export interface CompletenessItem {
  scope: string;
  id: string;
  label: string;
  field: string;
  message: string;
}

export interface DocumentInfo {
  id: string;
  original_name: string;
  mime: string;
  type_label: string;
  bytes: number;
  sha256: string;
  version: number;
  supersedes_id: string | null;
  readability: string;
  readability_label: string;
  inspection_notes: string[];
  previewable: boolean;
  uploaded_by: UserBrief;
  created_at: string;
}

export interface CaseDocument {
  id: string;
  usage: string;
  usage_label: string;
  added_by: UserBrief;
  created_at: string;
  replaced_by_id: string | null;
  row_version: number;
  document: DocumentInfo;
  latest_extraction?: ExtractionRun | null;
}

/** Localisation d'une valeur lue : page physique (depuis 1) et zone normalisée 0–1, ou feuille et cellule. */
export interface Span {
  id: string;
  document_id: string;
  page: number | null;
  bbox: [number, number, number, number] | null;
  page_size: [number, number] | null;
  rotation: number;
  sheet: string | null;
  cell_range: string | null;
  excerpt: string;
}

export interface FieldSource {
  observation_id: string;
  run_id: string;
  label: string;
  raw: string;
  status: "ok" | "missing" | "ambiguous" | "unreadable" | "truncated" | "low_confidence";
  origin: "read" | "ocr" | "inferred";
  confidence: number | null;
  notes: string[];
  span: Span | null;
}

export interface ReviewFlag {
  field: string;
  code: string;
  message: string;
}

export interface Correction {
  id: string;
  field: string;
  previous: { value: unknown; origin?: string | null };
  current: { value: unknown };
  reason: string;
  actor: string;
  at: string;
}

export interface Divergence {
  id: string;
  kind: "value" | "line_not_reread";
  kind_label: string;
  invoice_line_id: string | null;
  line_ordinal: number | null;
  field: string;
  current_value: unknown;
  extracted_value: unknown;
  run_id: string;
  state: "open" | "kept" | "accepted";
  state_label: string;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_reason: string;
  span: Span | null;
}

export interface TotalsCheck {
  status: "match" | "gap" | "incomplete" | "no_printed_total";
  goods_lines: number;
  goods_lines_without_amount: number;
  components: { goods: string | null; fees: string | null; discounts: string | null; taxes: string | null };
  computed_total: string | null;
  printed_total: string | null;
  gap: string | null;
  explanations: string[];
  subtotals_not_added: { label: string; amount: string | null; page: number | null }[];
}

export interface Job {
  id: string;
  kind: string;
  state: "queued" | "running" | "succeeded" | "failed";
  state_label: string;
  phase: string;
  progress: { done?: number; total?: number } & Record<string, unknown>;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  hint: string | null;
  note: string;
}

export interface RunWarning {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ExtractionRun {
  id: string;
  case_document_id: string;
  document_id: string;
  attempt: number;
  parser: string;
  parser_version: string;
  provider: string | null;
  model: string | null;
  options: Record<string, unknown>;
  status: "queued" | "running" | "succeeded" | "failed";
  status_label: string;
  error_code: string | null;
  error_message: string | null;
  hint: string | null;
  warnings: RunWarning[];
  invoice_id: string | null;
  previous_run_id: string | null;
  merge_report: Record<string, number | boolean>;
  created_by: string;
  created_at: string;
  finished_at: string | null;
  job: Job;
}

export interface ExtractionDetail extends ExtractionRun {
  charges: { kind: string; label: string; amount: string | null; page?: number | null }[];
  comparison: {
    previous_attempt: number;
    counts: { same: number; changed: number; new: number; not_reread: number };
    rows: { entity_key: string; field: string; label: string; previous: unknown; current: unknown; status: string }[];
  } | null;
}

export interface Proposal {
  id: string;
  rank: number;
  node_id: string;
  code: string;
  code_display: string;
  label: string;
  full_path: string;
  reasons: string[];
  notes: { id: string; scope: string; heading: string; excerpt: string; mentions_exclusion: boolean }[];
  distinguishing: { code: string; code_display?: string; label: string }[];
  retrieval_score: number | null;
}

export interface ProposalSet {
  id: string;
  goods_line_id: string;
  edition_id: string;
  edition_label: string;
  trigger: string;
  query: string;
  producer: string;
  is_ai: boolean;
  questions: string[];
  is_current: boolean;
  created_at: string;
  created_by: string;
  proposals: Proposal[];
}

export interface CodeObservation {
  id: string;
  field_label: string;
  raw_code: string;
  normalized_code: string | null;
  code_kind: "customs" | "supplier" | "ambiguous";
  code_kind_label: string;
  created_by: string;
  created_at: string;
  superseded_at: string | null;
}

export interface InvoiceLine {
  id: string;
  ordinal: number;
  source_reference: string;
  description_raw: string;
  quantity: string | null;
  unit: string;
  unit_price: string | null;
  amount: string | null;
  origin_country: string;
  entry_origin_label: string;
  evidence_document_id: string | null;
  evidence_page: number | null;
  evidence_note: string;
  row_version: number;
  codes: CodeObservation[];
  code_history: CodeObservation[];
  goods_line_ids: string[];
  entry_origin?: string;
  extraction_key?: string | null;
  field_origins?: Record<string, string>;
  review_flags?: ReviewFlag[];
  field_sources?: Record<string, FieldSource>;
  corrections?: Correction[];
}

export interface Invoice {
  id: string;
  ordinal: number;
  supplier_name: string;
  invoice_number: string;
  invoice_date: string | null;
  currency: string;
  incoterm: string;
  declared_total: string | null;
  document_id: string | null;
  row_version: number;
  lines: InvoiceLine[];
  field_origins?: Record<string, string>;
  review_flags?: ReviewFlag[];
  field_sources?: Record<string, FieldSource>;
  divergences?: Divergence[];
  totals_check?: TotalsCheck;
  latest_extraction_id?: string | null;
}

export interface CodeCheck {
  id: string;
  observed_code: string | null;
  observed_field: string | null;
  normalized_code: string | null;
  target_edition_id: string;
  target_edition_label: string;
  recognition_status: string;
  recognition_label: string;
  node: { id: string; code: string; code_display: string; label: string; full_path: string; declarable: boolean } | null;
  is_current: boolean;
  human_confirmation: "pending" | "confirmed" | "stale";
  operational_applicability: "verified" | "unverified";
  findings: Finding[];
  checked_at: string;
  checked_by: string;
}

export interface Decision {
  id: string;
  action: string;
  action_label: string;
  selected_code: string;
  selected_code_display: string;
  label: string;
  edition: { id: string; label: string };
  reason: string;
  evidence_refs: unknown[];
  actor: UserBrief;
  at: string;
  is_current: boolean;
  note: string;
}

export interface GoodsLine {
  id: string;
  ordinal: number;
  description: string;
  origin_country: string;
  regime: string;
  row_version: number;
  sources: { invoice_line_id: string; invoice_ordinal: number; line_ordinal: number; assigned_quantity: string | null; assigned_value: string | null }[];
  latest_check: CodeCheck | null;
  decision: Decision | null;
  decision_count: number;
}

export interface Revision {
  id: string;
  revision_no: number;
  state: string;
  state_label: string;
  mode: string;
  mode_label: string;
  territory: string;
  planned_declaration_date: string | null;
  regime: string;
  is_editable: boolean;
  row_version: number;
  target_edition: (EditionBrief & { warning: string | null }) | null;
  documents: CaseDocument[];
  invoices: Invoice[];
  goods_lines: GoodsLine[];
  completeness: { blocking: CompletenessItem[]; warnings: CompletenessItem[]; complete: boolean };
  status_note: string;
}

export interface CaseSummary {
  id: string;
  reference: string;
  title: string;
  importer: { id: string; name: string } | null;
  assigned_to: UserBrief | null;
  created_by: UserBrief;
  created_at: string;
  row_version: number;
  state: string;
  state_label: string;
  mode: string;
  revision_no: number;
}

export interface CaseDetail extends CaseSummary {
  revision: Revision;
}

export interface AuditEntry {
  id: string;
  at: string;
  actor: string | null;
  event_type: string;
  current: Record<string, unknown> | null;
}

export type Preview =
  | { kind: "pdf" | "image"; url: string; expires_at: string }
  | { kind: "unavailable"; message: string; notes: string[] }
  | {
      kind: "sheet";
      note: string;
      sheet_count: number;
      sheets: { name: string; truncated: boolean; rows: { row: number; cells: { ref: string; value: string | null; formula: string | null }[] }[] }[];
    };

export const api = {
  me: () => request<Me>("GET", "/me"),
  login: (email: string, password: string) => request<Me>("POST", "/auth/login", { email, password }),
  logout: () => request<void>("POST", "/auth/logout"),
  selectOrganization: (organization_id: string) =>
    request<Me>("POST", "/me/active-organization", { organization_id }),
  importers: () => request<Page<Importer>>("GET", "/importers"),
  createImporter: (data: Partial<Importer>) => request<Importer>("POST", "/importers", data),
  members: () => request<Page<Member>>("GET", "/organization/members"),
  searchTariffs: (q: string) =>
    request<{ results: SearchResult[] }>("GET", `/tariffs/search?q=${encodeURIComponent(q)}`),
  tariffNode: (id: string) => request<NodeDetail>("GET", `/tariffs/nodes/${id}`),
  tariffRecord: (id: string) => request<RecordDetail>("GET", `/tariffs/records/${id}`),
  editions: () => request<(EditionBrief & { warning: string | null })[]>("GET", "/tariffs/editions"),
  cases: (params: Record<string, string>) =>
    request<{ results: CaseSummary[]; states: [string, string][] }>(
      "GET",
      `/cases?${new URLSearchParams(Object.entries(params).filter(([, v]) => v))}`,
    ),
  createCase: (data: Record<string, unknown>) => request<CaseDetail>("POST", "/cases", data),
  caseDetail: (id: string) => request<CaseDetail>("GET", `/cases/${id}`),
  assignCase: (id: string, assignee_id: string | null, row_version: number) =>
    request<CaseSummary>("POST", `/cases/${id}/assign`, { assignee_id, row_version }),
  updateRevision: (id: string, data: Record<string, unknown>) => request<Revision>("PATCH", `/revisions/${id}`, data),
  caseAudit: (id: string) => request<{ results: AuditEntry[] }>("GET", `/cases/${id}/audit`),
  documentLimits: () => request<{ max_bytes: number; accepted: string[] }>("GET", "/documents/limits"),
  uploadDocument: (caseId: string, file: File, usage: string, duplicateAction = "", idempotencyKey = "") => {
    const form = new FormData();
    form.append("file", file);
    form.append("usage", usage);
    if (duplicateAction) form.append("duplicate_action", duplicateAction);
    return upload<CaseDocument>(
      `/cases/${caseId}/documents`,
      form,
      idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    );
  },
  reuseDocument: (caseId: string, document_id: string, usage: string) =>
    request<CaseDocument>("POST", `/cases/${caseId}/documents/reuse`, { document_id, usage }),
  replaceDocument: (linkId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return upload<CaseDocument>(`/case-documents/${linkId}/replace`, form);
  },
  documentPreview: (id: string) => request<Preview>("GET", `/documents/${id}/preview`),
  documentLink: (id: string) => request<{ url: string; expires_at: string }>("GET", `/documents/${id}/download`),
  addInvoice: (revisionId: string, data: Record<string, unknown>) =>
    request<Invoice>("POST", `/revisions/${revisionId}/invoices`, data),
  addLine: (invoiceId: string, data: Record<string, unknown>) =>
    request<InvoiceLine>("POST", `/invoices/${invoiceId}/lines`, data),
  updateLine: (lineId: string, data: Record<string, unknown>) =>
    request<InvoiceLine>("PATCH", `/invoice-lines/${lineId}`, data),
  addGoods: (revisionId: string, invoice_line_ids: string[]) =>
    request<GoodsLine>("POST", `/revisions/${revisionId}/goods-lines`, { invoice_line_ids }),
  updateGoods: (id: string, data: Record<string, unknown>) => request<GoodsLine>("PATCH", `/goods-lines/${id}`, data),
  checkCode: (goodsId: string, edition_id: string) =>
    request<CodeCheck>("POST", `/goods-lines/${goodsId}/code-checks`, { edition_id }),
  decide: (goodsId: string, data: Record<string, unknown>) =>
    request<GoodsLine>("POST", `/goods-lines/${goodsId}/decisions`, data),
  extract: (linkId: string, options: { ocr?: boolean; retry?: boolean }) =>
    request<ExtractionRun>("POST", `/case-documents/${linkId}/extractions`, options),
  extractionRun: (id: string) => request<ExtractionDetail>("GET", `/extraction-runs/${id}`),
  job: (id: string) => request<Job>("GET", `/jobs/${id}`),
  resolveDivergence: (id: string, resolution: "keep" | "accept", reason: string) =>
    request<Divergence>("POST", `/divergences/${id}/resolve`, { resolution, reason }),
  goodsFromInvoice: (invoiceId: string) =>
    request<{ results: GoodsLine[] }>("POST", `/invoices/${invoiceId}/goods-lines`, {}),
  proposals: (goodsId: string) => request<{ results: ProposalSet[] }>("GET", `/goods-lines/${goodsId}/proposals`),
  propose: (goodsId: string, data: { edition_id?: string; query?: string; explicit?: boolean }) =>
    request<ProposalSet>("POST", `/goods-lines/${goodsId}/proposals`, data),
};

export const ROLE_LABELS: Record<Role, string> = {
  declarant: "Déclarant",
  validator: "Validateur",
  org_admin: "Administrateur",
};
