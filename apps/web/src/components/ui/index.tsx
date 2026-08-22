"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("overflow-hidden rounded-lg border bg-card text-card-foreground", className)}
      {...props}
    />
  );
}

export function CardHeader({
  title,
  subtitle,
  actions,
  className,
}: Readonly<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}>) {
  return (
    <div
      className={cn(
        "flex flex-col gap-2 border-b px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-5",
        className,
      )}
    >
      <div className="min-w-0">
        <div className="text-base font-semibold leading-snug">{title}</div>
        {subtitle ? (
          <div className="mt-1 max-w-reading text-sm leading-relaxed text-muted-foreground">
            {subtitle}
          </div>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}

export function CardBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4 sm:p-5", className)} {...props} />;
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "dark" | "ghost" | "destructive";
  size?: "sm" | "md";
};

export function Button({
  className,
  variant = "default",
  size = "md",
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md border font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background",
        "disabled:cursor-not-allowed disabled:opacity-45",
        size === "sm" ? "h-8 rounded-md px-3 text-xs" : "h-9 px-3.5 text-sm",
        variant === "default" && "border-border bg-card hover:bg-muted",
        variant === "primary" &&
          "border-primary bg-primary text-primary-foreground hover:brightness-110",
        variant === "dark" &&
          "border-foreground bg-foreground text-background hover:opacity-90",
        variant === "ghost" && "border-transparent bg-transparent hover:bg-muted",
        variant === "destructive" &&
          "border-destructive bg-destructive text-destructive-foreground hover:brightness-110",
        className,
      )}
      {...props}
    />
  );
}

export type Tone = "neutral" | "good" | "warn" | "bad" | "novel" | "info";

/*
  Every pill carries a word, never colour alone. branding.md rules out green
  and red as the only status axis, so amber and indigo do real work here.
*/
export function Pill({
  tone = "neutral",
  className,
  children,
}: Readonly<{
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}>) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center whitespace-nowrap rounded-md border px-2 text-2xs font-medium",
        tone === "neutral" && "border-border bg-muted text-muted-foreground",
        tone === "good" && "border-primary/30 bg-primary/10 text-primary",
        tone === "warn" && "border-warning/40 bg-warning/15 text-warning-foreground dark:text-warning",
        tone === "bad" && "border-destructive/30 bg-destructive/10 text-destructive",
        tone === "novel" && "border-secondary/30 bg-secondary/10 text-secondary",
        tone === "info" && "border-info/30 bg-info/10 text-info",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Field({
  label,
  hint,
  error,
  required,
  children,
}: Readonly<{
  label: string;
  hint?: string | null;
  error?: string | null;
  required?: boolean;
  children: React.ReactNode;
}>) {
  return (
    <label className="block">
      <div className="mb-1.5 flex flex-wrap items-baseline gap-1.5">
        <span className="text-sm font-medium">{label}</span>
        {required ? <span className="text-2xs text-muted-foreground">required</span> : null}
      </div>
      {children}
      {hint && !error ? (
        <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
      ) : null}
      {error ? (
        <div className="mt-1 flex items-start gap-1 text-xs text-destructive">
          <span aria-hidden>&#9888;</span>
          <span>{error}</span>
        </div>
      ) : null}
    </label>
  );
}

export const inputClass =
  "w-full rounded-md border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(inputClass, "h-10", props.className)} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn(inputClass, "min-h-[6rem]", props.className)} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cn(inputClass, "h-10", props.className)} />;
}

export function Tabs({
  tabs,
  active,
  onChange,
}: Readonly<{
  tabs: { id: string; label: string; badge?: number }[];
  active: string;
  onChange: (id: string) => void;
}>) {
  return (
    <div
      className="-mx-4 flex items-center gap-1 overflow-x-auto border-b px-4 sm:mx-0 sm:px-0"
      role="tablist"
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={active === tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            "-mb-px flex h-10 shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 px-3 text-sm font-medium transition-colors",
            active === tab.id
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {tab.label}
          {tab.badge ? (
            <span className="rounded-sm bg-muted px-1 text-2xs text-muted-foreground">
              {tab.badge}
            </span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

export function Kpi({
  label,
  value,
  detail,
  tone = "neutral",
}: Readonly<{
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  tone?: Tone;
}>) {
  return (
    <div className="rounded-lg border bg-card p-4 sm:p-5">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-1.5 text-3xl font-semibold leading-none tracking-tight",
          tone === "bad" && "text-destructive",
          tone === "warn" && "text-warning",
          tone === "good" && "text-primary",
        )}
      >
        {value}
      </div>
      {detail ? <div className="mt-2 text-xs text-muted-foreground">{detail}</div> : null}
    </div>
  );
}

export function Empty({ title, detail }: Readonly<{ title: string; detail?: string }>) {
  return (
    <div className="px-4 py-12 text-center">
      <div className="text-sm font-medium">{title}</div>
      {detail ? (
        <div className="mx-auto mt-1.5 max-w-reading text-sm text-muted-foreground">{detail}</div>
      ) : null}
    </div>
  );
}

export function Spinner({ label = "Loading" }: Readonly<{ label?: string }>) {
  return (
    <div className="flex items-center gap-2.5 px-4 py-10 text-sm text-muted-foreground">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-primary" />
      {label}
    </div>
  );
}

export function DataState({
  loading,
  errorMessage,
  errorTitle = "That view is not available to you",
  isEmpty,
  emptyTitle = "Nothing in this view",
  children,
}: Readonly<{
  loading: boolean;
  errorMessage?: string | null;
  errorTitle?: string;
  isEmpty: boolean;
  emptyTitle?: string;
  children: React.ReactNode;
}>) {
  if (loading) return <Spinner />;
  if (errorMessage) return <Empty title={errorTitle} detail={errorMessage} />;
  if (isEmpty) return <Empty title={emptyTitle} />;
  return <>{children}</>;
}

export function PageTitle({
  title,
  subtitle,
  actions,
}: Readonly<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}>) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-secondary sm:text-3xl">
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-2 max-w-reading text-base leading-relaxed text-muted-foreground">
            {subtitle}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}

/*
  A refusal is shown as a refusal. It is never rendered as an empty answer,
  because an output without sources is a failed call, not a low-confidence one.
*/
export function Refusal({ title, reason, reasons }: Readonly<{ title: string; reason?: string | null; reasons?: string[] }>) {
  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 sm:p-5">
      <div className="flex items-center gap-2 text-base font-semibold text-destructive">
        <span aria-hidden>&#9940;</span>
        {title}
      </div>
      {reason ? <p className="mt-1.5 text-sm leading-relaxed">{reason}</p> : null}
      {reasons?.length ? (
        <ul className="mt-2 space-y-1 text-sm">
          {reasons.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="text-destructive" aria-hidden>
                &bull;
              </span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function Notice({
  tone = "info",
  title,
  children,
}: Readonly<{
  tone?: Tone;
  title: string;
  children?: React.ReactNode;
}>) {
  return (
    <div
      className={cn(
        "rounded-lg border p-3.5 sm:p-4",
        tone === "warn" && "border-warning/40 bg-warning/10",
        tone === "info" && "border-info/30 bg-info/5",
        tone === "good" && "border-primary/30 bg-primary/5",
        tone === "novel" && "border-secondary/30 bg-secondary/5",
        tone === "bad" && "border-destructive/30 bg-destructive/5",
        tone === "neutral" && "border-border bg-muted",
      )}
    >
      <div className="text-sm font-semibold sm:text-base">{title}</div>
      {children ? (
        <div className="mt-1.5 max-w-reading text-sm leading-relaxed">{children}</div>
      ) : null}
    </div>
  );
}

export function Mono({ children, className }: Readonly<{ children: React.ReactNode; className?: string }>) {
  return (
    <span className={cn("font-mono text-2xs tracking-tight text-muted-foreground", className)}>
      {children}
    </span>
  );
}

export function Row({
  cols,
  head,
  className,
  children,
}: Readonly<{
  cols: string;
  head?: boolean;
  className?: string;
  children: React.ReactNode;
}>) {
  return (
    <div
      style={{ gridTemplateColumns: cols }}
      className={cn(
        "grid items-center gap-3 px-4 sm:gap-4 sm:px-5",
        head
          ? "sticky top-16 z-10 border-b bg-muted py-3 text-xs font-medium uppercase tracking-wide text-muted-foreground"
          : "border-b py-3.5 text-sm last:border-b-0 hover:bg-muted/30",
        className,
      )}
    >
      {children}
    </div>
  );
}

/*
  One dialog serves every write action in the workspace. It traps nothing and
  steals no focus beyond the first control, because the actions behind it are
  short forms rather than applications in their own right. Escape closes it,
  the backdrop closes it, and the body stops scrolling while it is open.
*/
export function Modal({
  open,
  title,
  subtitle,
  onClose,
  footer,
  width = "md",
  children,
}: Readonly<{
  open: boolean;
  title: string;
  subtitle?: React.ReactNode;
  onClose: () => void;
  footer?: React.ReactNode;
  width?: "sm" | "md" | "lg";
  children: React.ReactNode;
}>) {
  const panel = React.useRef<HTMLDialogElement>(null);

  React.useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.querySelector<HTMLElement>("input, select, textarea, button")?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:items-center sm:p-6">
      <button
        type="button"
        aria-label="Close this dialog"
        className="fixed inset-0 cursor-default bg-background/80 backdrop-blur-sm"
        onClick={onClose}
      />
      <dialog
        ref={panel}
        open
        aria-modal="true"
        aria-label={title}
        className={cn(
          "relative w-full rounded-lg border bg-card text-card-foreground shadow-lg",
          width === "sm" && "max-w-md",
          width === "md" && "max-w-2xl",
          width === "lg" && "max-w-4xl",
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b px-5 py-4">
          <div className="min-w-0">
            <div className="text-base font-semibold">{title}</div>
            {subtitle ? (
              <div className="mt-1 max-w-reading text-sm leading-relaxed text-muted-foreground">
                {subtitle}
              </div>
            ) : null}
          </div>
          <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close">
            &#10005;
          </Button>
        </div>
        <div className="max-h-[70vh] space-y-4 overflow-y-auto p-5">{children}</div>
        {footer ? (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t bg-muted/30 px-5 py-3.5">
            {footer}
          </div>
        ) : null}
      </dialog>
    </div>
  );
}

/*
  A confirmation for the actions that cannot be taken back. It insists on a
  reason wherever the API insists on one, so the refusal arrives before the
  request rather than after it.
*/
export function Confirm({
  open,
  title,
  detail,
  confirmLabel = "Confirm",
  destructive,
  reasonLabel,
  busy,
  error,
  onCancel,
  onConfirm,
}: Readonly<{
  open: boolean;
  title: string;
  detail?: React.ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  reasonLabel?: string;
  busy?: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}>) {
  const [reason, setReason] = React.useState("");

  React.useEffect(() => {
    if (open) setReason("");
  }, [open]);

  const blocked = Boolean(reasonLabel) && reason.trim().length === 0;

  return (
    <Modal
      open={open}
      title={title}
      subtitle={detail}
      width="sm"
      onClose={onCancel}
      footer={
        <>
          <Button onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant={destructive ? "destructive" : "primary"}
            disabled={blocked || busy}
            onClick={() => onConfirm(reason.trim())}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {reasonLabel ? (
        <Field label={reasonLabel} required hint="Recorded on the audit trail.">
          <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
      ) : null}
      {error ? <Refusal title="That action was refused" reason={error} /> : null}
    </Modal>
  );
}

/* A row of write actions, hidden entirely when the role cannot use any. */
export function Actions({ children }: Readonly<{ children: React.ReactNode }>) {
  return <div className="flex flex-wrap items-center gap-2">{children}</div>;
}

export function KeyValue({
  rows,
}: Readonly<{ rows: readonly (readonly [string, React.ReactNode])[] }>) {
  return (
    <div className="space-y-2.5 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-3">
          <span className="text-muted-foreground">{label}</span>
          <span className="min-w-0 text-right font-medium">{value}</span>
        </div>
      ))}
    </div>
  );
}
