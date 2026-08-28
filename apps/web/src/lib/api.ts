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

/*
  Not every 401 means the session is over.

  A step-up refusal is a 401 because the caller is not authenticated *enough*
  for one particular act, and the authentication endpoints answer 401 for a
  wrong password or a wrong six-digit code. Treating any of those as a dead
  session signed people out at the exact moment they were proving who they
  were, which made both enrolment and step-up impossible to finish.
*/
function endsTheSession(status: number, code: string, path: string): boolean {
  if (status !== 401) return false;
  if (code === "step_up_required") return false;
  return !path.startsWith("/auth/");
}

function redirectToSignIn(): void {
  const here = globalThis.location;
  if (!here || here.pathname.startsWith("/sign-in")) return;
  here.assign("/sign-in?expired=1");
}

/* The platform's own refusal shape where there is one, FastAPI's `detail`
   where a framework-level error got there first, and the status on its own
   when the body is not JSON at all. */
async function readProblem(response: Response): Promise<ProblemDetail> {
  try {
    const parsed = await response.json();
    if (parsed && typeof parsed === "object" && "code" in parsed) return parsed as ProblemDetail;
    if (parsed?.detail) return { code: "error", message: String(parsed.detail) };
  } catch {
    // The response carried no JSON body.
  }
  return {
    code: "unexpected",
    message: `The request failed with status ${response.status}.`,
  };
}

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
    const problem = await readProblem(response);
    if (endsTheSession(response.status, problem.code, path)) {
      setToken(null);
      if (token) redirectToSignIn();
    }
    throw new ApiError(response.status, problem);
  }

  if (options.raw) return (await response.blob()) as unknown as T;
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const WORKSPACE_ROLES = new Set([
  "counsel",
  "head_of_legal",
  "finance",
  "procurement",
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
    // External counsel has one page and it is neither of the other two. They
    // are not staff, so the workspace would refuse every screen in it, and they
    // are not raising requests, so the portal has nothing for them.
    if (me.roles.includes("consultant") && !me.roles.some((role) => WORKSPACE_ROLES.has(role))) {
      return "/consultant";
    }
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
/* Multipart where the body is more than one file field. Same headers and the
   same error shaping as the rest, because a refusal from an upload has to read
   like every other refusal. */
export async function postForm<T>(path: string, form: FormData): Promise<T> {
  const headers: Record<string, string> = { "X-Entity": getEntity() };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${BASE}/api/v1${path}`, {
    method: "POST",
    headers,
    body: form,
    cache: "no-store",
  });

  if (!response.ok) {
    let problem: ProblemDetail = {
      code: "request_failed",
      message: `The request failed with status ${response.status}.`,
    };
    try {
      problem = (await response.json()) as ProblemDetail;
    } catch {
      // A response with no JSON body keeps the status-derived message.
    }
    throw new ApiError(response.status, problem);
  }

  return (await response.json()) as T;
}

export async function upload<T>(
  path: string,
  file: File,
  method: "POST" | "PUT" = "POST",
  field = "file",
): Promise<T> {
  const headers: Record<string, string> = { "X-Entity": getEntity() };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const form = new FormData();
  form.append(field, file);

  const response = await fetch(`${BASE}/api/v1${path}`, {
    method,
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

/* Viewing, rather than saving. Same problem as a download, in that the request
   has to carry the token, so the file is fetched as a blob and the blob opened
   in its own tab. The object URL is revoked on a timer instead of immediately,
   because revoking it before the new tab has read it leaves a blank window. */
export async function view(path: string): Promise<void> {
  const blob = await api<Blob>(path, { raw: true });
  const url = URL.createObjectURL(blob);

  /*
    An anchor rather than window.open, and not for style. Passing "noopener"
    to window.open makes it return null in several browsers even when the tab
    opened perfectly well, because the opener is deliberately given no handle
    on it. Treating that null as failure reported an error over a document
    that was already on screen, which teaches people to ignore the error.

    A click on an anchor carries the user gesture that opened it, so pop-up
    blockers allow it, and there is no return value to misread.
  */
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  document.body.append(link);
  link.click();
  link.remove();

  globalThis.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
