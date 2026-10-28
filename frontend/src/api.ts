// Client de l'API ClairTransit : session serveur (cookie HttpOnly) + jeton CSRF.
// Aucun jeton durable n'est stocké dans le navigateur.

export type Role = "declarant" | "validator" | "org_admin";

export interface Membership {
  organization: { id: string; name: string; is_demo: boolean; timezone: string; default_locale: "fr" | "en" | "es" | "ar" };
  roles: Role[];
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  is_reference_manager: boolean;
  /** Exploitant de la plateforme : console des sociétés, aucun accès à leurs dossiers. */
  is_platform_operator: boolean;
  memberships: Membership[];
  active_organization_id: string | null;
  interface_locale: "fr" | "en" | "es" | "ar";
  mfa_enabled: boolean;
  mfa_verified_session: boolean;
  mfa_required_for_access: boolean;
}

export interface Importer {
  id: string;
  name: string;
  identifiers: Record<string, string>;
  contacts: Record<string, string>[];
  address: string;
  notes: string;
  /** Le client refuse que ses pièces soient lues par une IA en ligne (prioritaire sur la société). */
  ai_refused?: boolean;
  ai_refused_at?: string | null;
  row_version: number;
  possible_duplicates?: { id: string; name: string }[];
}

export interface Member {
  id: string;
  email: string;
  full_name: string;
  roles: Role[];
  agency: string | null;
  agency_name: string | null;
  active: boolean;
  row_version: number;
}

export type BusinessProfile = "transit" | "importer" | "logistics" | "expert";
export type InvitationStatus = "pending" | "expired" | "accepted" | "revoked";

export interface Invitation {
  id: string;
  email: string;
  full_name: string;
  roles: Role[];
  agency: string | null;
  agency_name: string | null;
  expires_at: string;
  created_at: string;
  status: InvitationStatus;
  /** Rendu une seule fois, à la création ou au renouvellement : sert à composer le lien. */
  token?: string;
  /** Envoi du lien par e-mail, à la création ou au renouvellement. */
  email_status?: EmailStatus;
}

export type EmailStatus = "sent" | "failed" | "disabled" | "local_address" | "no_address";

export interface InvitationPreview {
  organization_name: string;
  email: string;
  full_name: string;
  roles: Role[];
  agency_name: string | null;
  expires_at: string;
  existing_account: boolean;
}

export interface Agency {
  id: string;
  name: string;
  code: string;
  country_code: string;
  active: boolean;
}

export interface OrganizationOverview {
  name: string;
  primary_profile: BusinessProfile;
  country_code: string;
  default_locale: string;
  max_users: number | null;
  seats_used: number;
  members: number;
  pending_invitations: number;
  agencies: number;
}

export interface AccessRequestInput {
  company_name: string;
  primary_profile: BusinessProfile;
  country_code: string;
  registration_number: string;
  contact_name: string;
  contact_role: string;
  contact_email: string;
  contact_phone: string;
  preferred_locale: string;
}

export interface AccessRequestInfo extends AccessRequestInput {
  id: string;
  status: "pending" | "accepted" | "refused";
  created_at: string;
  decided_at: string | null;
  decision_note: string;
  organization: string | null;
}

export interface PlatformOrganization {
  id: string;
  name: string;
  primary_profile: BusinessProfile;
  country_code: string;
  default_locale: string;
  active: boolean;
  is_demo: boolean;
  max_users: number | null;
  members: number;
  pending_invitations: number;
  admin_invitation: Invitation | null;
  created_at: string;
}

export interface NewOrganizationInput {
  name: string;
  primary_profile: BusinessProfile;
  country_code: string;
  default_locale: string;
  max_users: number | null;
  admin_name: string;
  admin_email: string;
}

/** Lien d'activation à copier : il marche sans e-mail ni internet sur le serveur de l'agence. */
export const activationLink = (token: string) =>
  `${window.location.origin}${window.location.pathname}#/activation/${encodeURIComponent(token)}`;

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

/** Émis quand la session a pris fin pendant l'utilisation (expiration, déconnexion dans un autre onglet). */
export const SESSION_ENDED_EVENT = "clairtransit:session-ended";

function watchSession(path: string, response: Response): Response {
  // /me et /auth/* répondent 401 normalement avant la connexion : seule une autre route signale une session perdue.
  if (response.status === 401 && path !== "/me" && !path.startsWith("/auth/")) {
    window.dispatchEvent(new Event(SESSION_ENDED_EVENT));
  }
  return response;
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
  return parse<T>(watchSession(path, response));
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
  return parse<T>(watchSession(path, response));
}

export interface EditionBrief {
  id: string;
  label: string;
  publication_state: "draft" | "consultation" | "operational" | "withdrawn";
}

export interface Edition extends EditionBrief {
  warning: string | null;
  hs_version?: string;
  effective_from?: string | null;
  applicability_verified?: boolean;
  published_at?: string | null;
  source?: { title: string; kind_label: string; is_derived_copy: boolean };
}

export interface ImportRunInfo {
  id: string;
  source: string;
  source_kind: string;
  importer_name: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  counts: { tariff_lines?: number; issues?: Record<string, number> } & Record<string, unknown>;
  edition_id: string | null;
  open_issues: number;
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
  detected_locale?: "fr" | "en" | "es" | "ar" | "";
  language_detection?: { locale: string; status: string; method: string; pages?: { page: number | null; locale: string; status: string }[]; zones?: { page: number | null; row: number; locale: string }[] };
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
  /** Type de la pièce : confirmé par un agent, reconnu d'après le titre, ou déduit de l'usage. */
  document_type?: PieceType | null;
  /** Titre lu qui contredit l'usage choisi au dépôt ; jamais appliqué sans confirmation. */
  type_mismatch?: Omit<PieceType, "source"> | null;
  latest_extraction?: ExtractionRun | null;
}

export interface PieceType {
  code: string;
  label: string;
  label_en: string;
  source: "confirmed" | "detected" | "usage";
  evidence: { method?: "title" | "filename"; excerpt?: string; reason?: string };
}

/** Information lue sur une pièce autre qu'une facture (B/L, assurance, fret). */
export interface DocumentField {
  field: string;
  label: string;
  raw: string | null;
  parsed: unknown;
  status: FieldSource["status"];
  origin: FieldSource["origin"];
  notes: string[];
  span: Span | null;
  /** Proposition de l'IA en ligne pour une information non trouvée : à vérifier. */
  proposal?: AIProposal | null;
  /** Valeur retenue ou saisie par un agent. */
  entered?: { raw: string | null; from_ai: boolean; by: string; at: string } | null;
}

export interface AIProposal {
  raw: string | null;
  parsed: unknown;
  status: FieldSource["status"];
  notes: string[];
  excerpt: string;
  span: Span | null;
  created_at: string;
}

export interface AIState {
  last: {
    status: "sent" | "client_refused" | "cap_reached" | "failed";
    status_label: string;
    trigger: "auto" | "on_demand";
    provider: string | null;
    provider_label: string | null;
    model: string | null;
    free_tier: boolean;
    requested: number;
    found: number;
    rejected: number;
    error_message: string | null;
    created_at: string;
  } | null;
  client_refused: boolean;
  can_complete: boolean;
  missing: string[];
  /** Facture : propositions pour les champs d'en-tête restés vides. */
  proposals: (AIProposal & { field: string; label: string })[];
}

export interface AISettings {
  enabled: boolean;
  mode: "auto" | "on_demand";
  monthly_cap: number;
  row_version: number;
  provider: { name: string | null; label: string | null; model: string | null; configured: boolean; free_tier: boolean };
  usage: { month_start: string; sent: number; cap: number; cost_estimate: string | null };
  refusing_clients: { id: string; name: string; refused_at: string | null; refused_by: string | null }[];
  journal: {
    id: string;
    created_at: string;
    case_id: string;
    case_reference: string;
    file_name: string;
    usage: string;
    detected_type: string | null;
    status: "sent" | "client_refused" | "cap_reached" | "failed";
    status_label: string;
    trigger: "auto" | "on_demand";
    provider: string | null;
    model: string | null;
    free_tier: boolean;
    requested: number;
    found: number;
    rejected: number;
    cost_estimate: string | null;
    error_message: string | null;
    by: string;
  }[];
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
  origin: "read" | "ocr" | "inferred" | "ai";
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
  reader?: "invoice" | "transport" | "insurance" | "freight";
  fields?: DocumentField[];
  ai?: AIState;
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
  buyer_name?: string;
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
  client_reference?: string;
  transport_mode?: string;
  transport_mode_label?: string;
  entry_office?: string;
  origin_country?: string;
  provenance_country?: string;
  priority?: string;
  priority_label?: string;
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

export interface OrgAuditEvent {
  id: string;
  at: string;
  actor_email: string | null;
  event_type: string;
  entity_type: string;
  entity_id: string;
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

// ---- Numérisation : lots du scanner et photos, découpés en pièces avant rattachement --------

export type ScanSource = "scanner" | "camera";

export interface ScanCounts {
  pages: number;
  pending: number;
  kept: number;
  unclassified: number;
  blank_removed: number;
  hard_to_read: number;
  pieces: number;
}

export interface ScanBatchSummary {
  id: string;
  case_id: string;
  source: ScanSource;
  source_label: string;
  label: string;
  state: "open" | "processing" | "to_sort" | "attached" | "cancelled";
  state_label: string;
  created_by: UserBrief;
  created_at: string;
  attached_at: string | null;
  job: { state: Job["state"]; phase: string; progress: Job["progress"]; error_message: string | null } | null;
  counts: ScanCounts;
}

export interface ScanPageInfo {
  id: string;
  number: number | null;
  source_name: string;
  source_page: number;
  state: "pending" | "read" | "failed";
  state_label: string;
  rotation: number;
  blank: boolean;
  hard_to_read: boolean;
  removed: "" | "blank" | "user" | "replaced";
  removed_label: string;
  replaces_id: string | null;
  title: string;
  reference: string;
  page_marker: string;
  text_origin: string;
  notes: string[];
  piece_id: string | null;
  has_image: boolean;
}

export interface ScanPiece {
  id: string;
  ordinal: number;
  usage: string;
  usage_label: string;
  reason: string;
  usage_by_user: boolean;
  page_ids: string[];
  case_document: CaseDocument | null;
}

export interface ScanBatch extends ScanBatchSummary {
  sources: { id: string; name: string; page_count: number | null; error: string }[];
  pieces: ScanPiece[];
  pages: ScanPageInfo[];
  max_pages: number;
}

/** Image d'une page (servie par l'API, tournée comme l'agent l'a choisi). */
export const scanPageImage = (page: Pick<ScanPageInfo, "id" | "rotation">, thumb = true) =>
  `${BASE}/scan-pages/${page.id}/image?${thumb ? "size=thumb&" : ""}r=${page.rotation}`;

export const api = {
  me: () => request<Me>("GET", "/me"),
  login: (email: string, password: string) => request<Me | { mfa_required: true }>("POST", "/auth/login", { email, password }),
  verifyMfa: (code: string) => request<Me>("POST", "/auth/mfa/verify", { code }),
  setupMfa: () => request<{ secret: string; provisioning_uri: string }>("POST", "/auth/mfa/setup"),
  confirmMfa: (code: string) => request<{ enabled: boolean; recovery_codes: string[] }>("POST", "/auth/mfa/confirm", { code }),
  logout: () => request<void>("POST", "/auth/logout"),
  selectOrganization: (organization_id: string) =>
    request<Me>("POST", "/me/active-organization", { organization_id }),
  importers: () => request<Page<Importer>>("GET", "/importers"),
  createImporter: (data: Partial<Importer>) => request<Importer>("POST", "/importers", data),
  setImporterAIRefusal: (id: string, refused: boolean) =>
    request<Importer>("PUT", `/importers/${id}/ai-refusal`, { refused }),
  aiSettings: () => request<AISettings>("GET", "/organization/ai-settings"),
  saveAISettings: (data: { enabled: boolean; mode: AISettings["mode"]; monthly_cap: number; row_version: number }) =>
    request<AISettings>("PUT", "/organization/ai-settings", data),
  completeWithAI: (linkId: string) => request<ExtractionRun>("POST", `/case-documents/${linkId}/ai-completion`),
  decideField: (runId: string, field: string, action: "accept" | "set", value = "") =>
    request<ExtractionRun>("POST", `/extraction-runs/${runId}/fields/${field}/decision`, { action, value }),
  members: () => request<Page<Member>>("GET", "/organization/members"),
  reactivateMember: (id: string) => request<Member>("POST", `/organization/members/${id}/reactivate`),
  deactivateMember: (id: string) => request<Member>("POST", `/organization/members/${id}/deactivate`),
  setMemberAgency: (id: string, agency_id: string | null) =>
    request<Member>("PUT", `/organization/members/${id}/agency`, { agency_id }),
  organizationOverview: () => request<OrganizationOverview>("GET", "/organization/overview"),
  invitations: () => request<Invitation[]>("GET", "/organization/invitations"),
  invite: (data: { email: string; full_name: string; roles: Role[]; agency_id: string | null }) =>
    request<Invitation>("POST", "/organization/invitations", data),
  invitationAction: (id: string, action: "renew" | "revoke") =>
    request<Invitation>("POST", `/organization/invitations/${id}/${action}`),
  agencies: () => request<Agency[]>("GET", "/organization/agencies"),
  createAgency: (data: { name: string; code: string }) => request<Agency>("POST", "/organization/agencies", data),
  setupStatus: () => request<{ needs_setup: boolean }>("GET", "/auth/setup"),
  setup: (data: { full_name: string; email: string; password: string }) => request<Me>("POST", "/auth/setup", data),
  requestAccess: (data: AccessRequestInput) => request<{ received: true }>("POST", "/auth/access-requests", data),
  lookupInvitation: (token: string) => request<InvitationPreview>("POST", "/auth/invitations/lookup", { token }),
  acceptInvitation: (data: { token: string; full_name: string; password: string }) =>
    request<Me>("POST", "/auth/invitations/accept", data),
  accessRequests: (status = "") =>
    request<AccessRequestInfo[]>("GET", `/platform/access-requests${status ? `?status=${status}` : ""}`),
  acceptAccessRequest: (id: string) =>
    request<{ organization_id: string; invitation: Invitation }>("POST", `/platform/access-requests/${id}/accept`),
  refuseAccessRequest: (id: string, note: string) =>
    request<AccessRequestInfo>("POST", `/platform/access-requests/${id}/refuse`, { note }),
  platformOrganizations: () => request<PlatformOrganization[]>("GET", "/platform/organizations"),
  createOrganization: (data: NewOrganizationInput) =>
    request<{ organization_id: string; invitation: Invitation }>("POST", "/platform/organizations", data),
  setOrganizationState: (id: string, action: "suspend" | "reactivate") =>
    request<{ active: boolean }>("POST", `/platform/organizations/${id}/${action}`),
  renewAdminInvitation: (id: string) => request<Invitation>("POST", `/platform/invitations/${id}/renew`),
  searchTariffs: (q: string) =>
    request<{ results: SearchResult[] }>("GET", `/tariffs/search?q=${encodeURIComponent(q)}`),
  tariffNode: (id: string) => request<NodeDetail>("GET", `/tariffs/nodes/${id}`),
  tariffRecord: (id: string) => request<RecordDetail>("GET", `/tariffs/records/${id}`),
  editions: () => request<Edition[]>("GET", "/tariffs/editions"),
  importRuns: () => request<Page<ImportRunInfo>>("GET", "/reference-imports"),
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
  auditEvents: () => request<Page<OrgAuditEvent>>("GET", "/audit-events"),
  caseAudit: (id: string) => request<{ results: AuditEntry[] }>("GET", `/cases/${id}/audit`),
  documentLimits: () => request<{ max_bytes: number; accepted: string[] }>("GET", "/documents/limits"),
  /** usage : « auto » pour reconnaître le type d'après le titre ; documentType : type choisi par l'agent. */
  uploadDocument: (caseId: string, file: File, usage: string, duplicateAction = "", idempotencyKey = "", documentType = "") => {
    const form = new FormData();
    form.append("file", file);
    form.append("usage", usage);
    if (documentType) form.append("document_type", documentType);
    if (duplicateAction) form.append("duplicate_action", duplicateAction);
    return upload<CaseDocument>(
      `/cases/${caseId}/documents`,
      form,
      idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    );
  },
  reuseDocument: (caseId: string, document_id: string, usage: string, document_type = "") =>
    request<CaseDocument>("POST", `/cases/${caseId}/documents/reuse`, { document_id, usage, ...(document_type ? { document_type } : {}) }),
  confirmDocumentType: (linkId: string, document_type: string, reason: string) =>
    request("POST", `/case-documents/${linkId}/confirm-type`, { document_type, reason }),
  documentTypes: () => request<{ results: { code: string; label_fr: string; label_en: string; family: string }[] }>("GET", "/document-types"),
  documentPolicies: () => request<{ results: { document_type: string; active: boolean }[] }>("GET", "/organization/document-policies"),
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
  documentIntelligence: (revisionId: string) =>
    request<DocumentIntelligence>("GET", "/revisions/" + revisionId + "/document-intelligence"),
  analyzeDocuments: (revisionId: string) =>
    request<DocumentIntelligence>("POST", "/revisions/" + revisionId + "/document-intelligence", {}),
  addDocumentInvoiceLink: (revisionId: string, document_id: string, invoice_id: string, kind: string) =>
    request<GraphAssociation>("POST", "/revisions/" + revisionId + "/document-invoice-links",
      { document_id, invoice_id, kind }),
  addShipment: (revisionId: string, reference: string) =>
    request<{ id: string }>("POST", "/revisions/" + revisionId + "/shipments", { reference }),
  addShipmentAssociation: (revisionId: string, shipmentId: string, target_type: string, target_id: string) =>
    request<GraphAssociation>("POST", "/revisions/" + revisionId + "/shipments/" + shipmentId + "/links",
      { target_type, target_id }),
  reviewGraphLink: (model: string, id: string, status: "confirmed" | "rejected") =>
    request<GraphAssociation>("POST", "/document-intelligence/links/" + model + "/" + id + "/review",
      { status }),
  confirmGraphShipment: (id: string) =>
    request<{ id: string }>("POST", "/document-intelligence/shipments/" + id + "/confirm", {}),
  resolveGraphConflict: (id: string, reason: string) =>
    request<{ id: string }>("POST", "/document-intelligence/conflicts/" + id + "/resolve", { reason }),
  proposals: (goodsId: string) => request<{ results: ProposalSet[] }>("GET", `/goods-lines/${goodsId}/proposals`),
  propose: (goodsId: string, data: { edition_id?: string; query?: string; explicit?: boolean }) =>
    request<ProposalSet>("POST", `/goods-lines/${goodsId}/proposals`, data),
  scanBatches: (caseId: string) =>
    request<{ results: ScanBatchSummary[]; max_pages: number }>("GET", `/cases/${caseId}/scan-batches`),
  createScanBatch: (caseId: string, source: ScanSource, label = "") =>
    request<ScanBatch>("POST", `/cases/${caseId}/scan-batches`, { source, label }),
  scanBatch: (id: string) => request<ScanBatch>("GET", `/scan-batches/${id}`),
  addScanFiles: (id: string, files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return upload<ScanBatch>(`/scan-batches/${id}/files`, form);
  },
  addScanPhoto: (id: string, file: Blob, target: { piece_id?: string; usage?: string }) => {
    const form = new FormData();
    form.append("file", file, file instanceof File ? file.name : "photo.jpg");
    if (target.piece_id) form.append("piece_id", target.piece_id);
    if (target.usage) form.append("usage", target.usage);
    return upload<{ page_id: string; batch: ScanBatch }>(`/scan-batches/${id}/photos`, form);
  },
  scanAction: (id: string, action: "finish" | "attach" | "cancel") =>
    request<ScanBatch>("POST", `/scan-batches/${id}/${action}`, {}),
  updateScanPage: (id: string, data: { rotation?: number; removed?: boolean; piece_id?: string | null; usage?: string }) =>
    request<ScanBatch>("PATCH", `/scan-pages/${id}`, data),
  splitScanPage: (id: string) => request<ScanBatch>("POST", `/scan-pages/${id}/split`, {}),
  replaceScanPage: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return upload<ScanBatch>(`/scan-pages/${id}/replace`, form);
  },
  updateScanPiece: (id: string, usage: string) => request<ScanBatch>("PATCH", `/scan-pieces/${id}`, { usage }),
  joinScanPiece: (id: string) => request<ScanBatch>("POST", `/scan-pieces/${id}/join-previous`, {}),
};

export const ROLE_LABELS: Record<Role, string> = {
  declarant: "Déclarant",
  validator: "Validateur",
  org_admin: "Administrateur",
};


export interface GraphAssociation {
  id: string;
  status: "proposed" | "confirmed" | "rejected";
  evidence: { kind?: string; value?: string; method?: string }[];
  reviewed_at: string | null;
  document_id?: string;
  invoice_id?: string;
  shipment_id?: string;
  revision_id?: string;
  kind?: string;
}

export interface DocumentIntelligence {
  revision_id: string;
  engine: string;
  ai_provider: string;
  shipments: {
    id: string;
    reference: string;
    status: "proposed" | "confirmed";
    method: string;
    documents: GraphAssociation[];
    invoices: GraphAssociation[];
  }[];
  document_invoices: GraphAssociation[];
  conflicts: {
    id: string;
    kind: string;
    document_id: string | null;
    invoice_id: string | null;
    status: "open" | "resolved";
    detail: Record<string, string>;
    resolution: string;
  }[];
  pending_count: number;
  created?: Record<string, number>;
}
