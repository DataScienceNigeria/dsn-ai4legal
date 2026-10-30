import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function firstName(name: string | null | undefined): string {
  return (name ?? "").trim().split(/\s+/)[0] ?? "";
}

export function initials(name: string): string {
  const parts = name.split(" ").filter(Boolean);
  return parts.slice(0, 2).map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

export function titleCase(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "Not set";
  return new Date(value).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Not set";
  return new Date(value).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatMoney(amount: number | null | undefined, currency = "NGN"): string {
  if (amount === null || amount === undefined) return "Not stated";
  return new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

/*
  The rule a typed amount must meet, mirrored by `number_problem` in the API's
  requests module: no sign, at most thirteen whole digits, which is what a
  float carries into NUMERIC(18, 2) exactly, and at most two decimal places.
*/
export const AMOUNT_PATTERN = /^\d{0,13}(\.\d{0,2})?$/;

export function groupDigits(raw: string): string {
  const [whole, fraction] = raw.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return fraction === undefined ? grouped : `${grouped}.${fraction}`;
}

export function relativeHours(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)} minutes`;
  if (hours < 48) return `${Math.round(hours)} hours`;
  return `${Math.round(hours / 24)} days`;
}

export type DecisionTone = "good" | "bad" | "warn" | "neutral";

export function decisionTone(status: string): DecisionTone {
  if (status === "approved" || status === "completed") return "good";
  if (status === "refused" || status === "rejected") return "bad";
  if (status === "pending") return "warn";
  return "neutral";
}

export function dueTone(days: number, leadTimeDays: number): DecisionTone {
  if (days < 0) return "bad";
  if (days <= leadTimeDays) return "warn";
  return "neutral";
}

export function percent(value: number | null): string {
  if (value === null) return "No reading";
  return `${Math.round(value * 100)}%`;
}

/*
  Fixed hues per organisation, and deliberately not --brand.

  --brand is whichever organisation you are currently in, which is right for
  everything that acts: a button, a tab, a selected row. It is useless anywhere
  both organisations appear at once, because then both are the same colour and
  the colour says nothing. The entity switcher was the first such place; the
  organisation particulars screen was the second, and titling both cards in
  --brand made two near-identical names look like one record listed twice.

  DSN is the brand blue, EqualyzAI the brand green, whichever organisation the
  reader happens to be working in.
*/
export const ENTITY_TONE: Record<string, { mark: string; chip: string; edge: string }> = {
  DSN: {
    mark: "bg-info",
    chip: "bg-info text-info-foreground",
    edge: "border-l-4 border-l-info",
  },
  EAI: {
    mark: "bg-primary",
    chip: "bg-primary text-primary-foreground",
    edge: "border-l-4 border-l-primary",
  },
};

export function entityTone(code: string) {
  return (
    ENTITY_TONE[code] ?? {
      mark: "bg-muted-foreground",
      chip: "bg-muted text-muted-foreground",
      edge: "border-l-4 border-l-border",
    }
  );
}

/*
  The password rule, mirrored by `new_password_problem` in the API's auth
  module: twelve to two hundred characters, not the current password and not
  the email address.
*/
export const MINIMUM_PASSWORD = 12;
export const MAXIMUM_PASSWORD = 200;

export function newPasswordProblem(next: string, current: string, email: string): string | null {
  if (!next) return "Choose a new password.";
  if (next.length < MINIMUM_PASSWORD) return `Use at least ${MINIMUM_PASSWORD} characters.`;
  if (next.length > MAXIMUM_PASSWORD) return `Use at most ${MAXIMUM_PASSWORD} characters.`;
  if (next === current) return "Choose a password different from the current one.";
  if (next.trim().toLowerCase() === email.trim().toLowerCase()) {
    return "Your email address cannot be your password.";
  }
  return null;
}

export const ENTITY_NAMES: Record<string, string> = {
  DSN: "Data Science Nigeria",
  EAI: "EqualyzAI",
};

export const ROLE_LABELS: Record<string, string> = {
  requester: "Requester",
  management: "Management",
  counsel: "Legal",
  head_of_legal: "Legal lead",
  finance: "Finance",
  procurement: "Procurement",
  consultant: "Legal consultant",
  admin: "Administrator",
  auditor: "Auditor",
  counterparty: "Counterparty",
};
