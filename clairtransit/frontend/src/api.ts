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
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, data.code ?? "ERROR", data.message ?? "Erreur inattendue.", data.details);
  }
  return data as T;
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
};

export const ROLE_LABELS: Record<Role, string> = {
  declarant: "Déclarant",
  validator: "Validateur",
  org_admin: "Administrateur",
};
