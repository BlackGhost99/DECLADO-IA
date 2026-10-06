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

export const api = {
  me: () => request<Me>("GET", "/me"),
  login: (email: string, password: string) => request<Me>("POST", "/auth/login", { email, password }),
  logout: () => request<void>("POST", "/auth/logout"),
  selectOrganization: (organization_id: string) =>
    request<Me>("POST", "/me/active-organization", { organization_id }),
  importers: () => request<Page<Importer>>("GET", "/importers"),
  createImporter: (data: Partial<Importer>) => request<Importer>("POST", "/importers", data),
  members: () => request<Page<Member>>("GET", "/organization/members"),
};

export const ROLE_LABELS: Record<Role, string> = {
  declarant: "Déclarant",
  validator: "Validateur",
  org_admin: "Administrateur",
};
