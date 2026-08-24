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
