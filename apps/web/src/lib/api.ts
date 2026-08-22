"use client";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const TOKEN_KEY = "dsn-lai-token";
const ENTITY_KEY = "dsn-lai-entity";

export type ProblemDetail = {
  code: string;
  message: string;
  field_errors?: Record<string, string>;
  reasons?: string[];
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly problem: ProblemDetail,
  ) {
    super(problem.message);
  }

  get fieldErrors(): Record<string, string> {
    return this.problem.field_errors ?? {};
  }

  get reasons(): string[] {
    return this.problem.reasons ?? [];
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return globalThis.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) globalThis.localStorage.setItem(TOKEN_KEY, token);
  else globalThis.localStorage.removeItem(TOKEN_KEY);
}

export function getEntity(): string {
  if (typeof window === "undefined") return "EAI";
  return globalThis.localStorage.getItem(ENTITY_KEY) ?? "EAI";
}

export function setEntity(entity: string) {
  if (typeof window === "undefined") return;
  globalThis.localStorage.setItem(ENTITY_KEY, entity);
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  entity?: string;
  raw?: boolean;
};

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "X-Entity": options.entity ?? getEntity() };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(`${BASE}/api/v1${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
  });

  if (!response.ok) {
    let problem: ProblemDetail = {
      code: "unexpected",
      message: `The request failed with status ${response.status}.`,
    };
    try {
      const parsed = await response.json();
      if (parsed && typeof parsed === "object" && "code" in parsed) problem = parsed;
      else if (parsed?.detail) problem = { code: "error", message: String(parsed.detail) };
    } catch {
      // The response carried no JSON body, so the default stands.
    }
    if (response.status === 401) setToken(null);
    throw new ApiError(response.status, problem);
  }

  if (options.raw) return (await response.blob()) as unknown as T;
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const WORKSPACE_ROLES = new Set([
  "legal_ops",
  "counsel",
  "head_of_legal",
  "privacy",
  "admin",
  "auditor",
  "management",
]);

/* Returns where this account belongs, so a requester is never shown a
   workspace that would refuse every screen in it. */
export async function login(
  email: string,
  password: string,
  code?: string,
): Promise<string> {
  const result = await api<{ access_token: string }>("/auth/token", {
    method: "POST",
    body: { email, password, code: code || undefined },
  });
  setToken(result.access_token);

  try {
    const me = await api<{ roles: string[] }>("/auth/me");
    const belongs = me.roles.some((role) => WORKSPACE_ROLES.has(role));
    return belongs ? "/workspace" : "/portal";
  } catch {
    return "/workspace";
  }
}

export async function stepUp(
  email: string,
  password: string,
  code?: string,
): Promise<void> {
  const result = await api<{ access_token: string }>("/auth/step-up", {
    method: "POST",
    body: { email, password, code: code || undefined },
  });
  setToken(result.access_token);
}

export function logout() {
  setToken(null);
}

/* Query strings are built here so a caller never hand-concatenates one and
   never forgets to encode a value that carries a space or an ampersand. */
export function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/* Multipart cannot go through api() because the body is a FormData and the
   browser must set the boundary itself. Everything else stays identical. */
export async function upload<T>(path: string, file: File, field = "file"): Promise<T> {
  const headers: Record<string, string> = { "X-Entity": getEntity() };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const form = new FormData();
  form.append(field, file);

  const response = await fetch(`${BASE}/api/v1${path}`, {
    method: "POST",
    headers,
    body: form,
    cache: "no-store",
  });

  if (!response.ok) {
    let problem: ProblemDetail = {
      code: "unexpected",
      message: `The upload failed with status ${response.status}.`,
    };
    try {
      const parsed = await response.json();
      if (parsed && typeof parsed === "object" && "code" in parsed) problem = parsed;
      else if (parsed?.detail) problem = { code: "error", message: String(parsed.detail) };
    } catch {
      // No JSON body, so the default message stands.
    }
    if (response.status === 401) setToken(null);
    throw new ApiError(response.status, problem);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/* A download has to carry the Authorization header, so it cannot be a plain
   link. The blob is handed to the browser and the object URL revoked after. */
export async function download(path: string, filename: string): Promise<void> {
  const blob = await api<Blob>(path, { raw: true });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
