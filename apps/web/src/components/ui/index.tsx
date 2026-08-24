"use client";

import Link from "next/link";
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
          "border-brand bg-brand text-brand-foreground hover:brightness-110",
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

/*
  A password field nobody can read is a password field people mistype, and a
  mistyped password at a step-up looks exactly like a refusal. The reveal is a
  button rather than a checkbox so it reaches the keyboard in the same tab
  order as the field it belongs to, and it says which state it is in rather
  than relying on the icon alone.
*/
export function PasswordInput({
  className,
  ...props
}: Readonly<Omit<React.InputHTMLAttributes<HTMLInputElement>, "type">>) {
  const [visible, setVisible] = React.useState(false);

  return (
    <div className="relative">
      <input
        {...props}
        type={visible ? "text" : "password"}
        className={cn(inputClass, "h-10 pr-11", className)}
      />
      <button
        type="button"
        onClick={() => setVisible((previous) => !previous)}
        aria-pressed={visible}
        aria-label={visible ? "Hide the password" : "Show the password"}
        title={visible ? "Hide the password" : "Show the password"}
        className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-md text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className="h-[1.15rem] w-[1.15rem]"
        >
          <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z" />
          <circle cx="12" cy="12" r="2.75" />
          {visible ? <path d="m4 20 16-16" /> : null}
        </svg>
      </button>
    </div>
  );
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
              ? "border-brand text-brand"
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

/*
  A figure on a dashboard is a question, and the answer is a list somewhere
  else. Where a `href` is given the whole tile becomes the link to that list,
  rather than leaving the reader to work out which menu item holds the records
  behind the number.
*/
export function Kpi({
  label,
  value,
  detail,
  tone = "neutral",
  href,
}: Readonly<{
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  tone?: Tone;
  href?: string;
}>) {
  const body = (
    <>
      <div className="flex items-baseline gap-1.5">
        <span className="text-sm text-muted-foreground">{label}</span>
        {href ? (
          <span aria-hidden className="text-xs text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
            &rarr;
          </span>
        ) : null}
      </div>
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
    </>
  );

  if (!href) {
    return <div className="rounded-lg border bg-card p-4 sm:p-5">{body}</div>;
  }

  return (
    <Link
      href={href}
      className="group block rounded-lg border bg-card p-4 text-foreground no-underline transition-colors hover:border-heading sm:p-5"
    >
      {body}
    </Link>
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
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-brand" />
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

/*
  One screen, one obvious next step. Where a screen has several things you can
  do, only the next one is a filled button; the rest go behind More. Seven
  buttons of equal weight is the same as none, because nothing among them says
  which one you came here to press.
*/
export function More({ children, label = "More" }: Readonly<{ children: React.ReactNode; label?: string }>) {
  const [open, setOpen] = React.useState(false);
  const box = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    function away(event: MouseEvent) {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return (
    <div ref={box} className="relative">
      <Button aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen((was) => !was)}>
        {label}
        <span aria-hidden className="text-xs">&#9662;</span>
      </Button>
      {open ? (
        <div
          role="menu"
          onClick={() => setOpen(false)}
          /*
            Children are laid out as menu rows whatever they are, so a
            component that renders its own trigger button can be dropped in
            without knowing it is inside a menu.
          */
          className="absolute right-0 z-40 mt-1.5 flex w-max min-w-[14rem] flex-col gap-0.5 rounded-lg border bg-popover p-1.5 shadow-lg [&_a]:w-full [&_button]:h-9 [&_button]:w-full [&_button]:justify-start [&_button]:border-transparent [&_button]:bg-transparent [&_button]:font-normal [&_button]:hover:bg-muted"
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

export function MenuItem({
  onClick,
  href,
  tone = "default",
  children,
}: Readonly<{
  onClick?: () => void;
  href?: string;
  tone?: "default" | "destructive";
  children: React.ReactNode;
}>) {
  const style = cn(
    "flex w-full items-center gap-2 whitespace-nowrap rounded-md px-2.5 py-2 text-left text-sm no-underline transition-colors",
    tone === "destructive"
      ? "text-destructive hover:bg-destructive/10"
      : "text-foreground hover:bg-muted",
  );
  if (href) {
    return (
      <Link role="menuitem" href={href} className={style}>
        {children}
      </Link>
    );
  }
  return (
    <button role="menuitem" type="button" onClick={onClick} className={style}>
      {children}
    </button>
  );
}

/*
  A short, fixed set of filters reads better as chips than as a select. The
  options are visible without opening anything, the current one is obvious, and
  choosing is one press rather than three.
*/
export function Chips({
  options,
  active,
  onChange,
  label = "Filter",
}: Readonly<{
  options: { id: string; label: string; count?: number }[];
  active: string;
  onChange: (id: string) => void;
  label?: string;
}>) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={label}>
      {options.map((option) => {
        const on = option.id === active;
        return (
          <button
            key={option.id}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(option.id)}
            className={cn(
              "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-full border px-3.5 text-xs font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background",
              on
                ? "border-brand bg-brand text-brand-foreground"
                : "border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {option.label}
            {typeof option.count === "number" ? (
              <span className={cn("text-2xs", on ? "opacity-80" : "opacity-70")}>{option.count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export type TimelineStep = {
  id: string;
  title: string;
  detail?: React.ReactNode;
  meta?: React.ReactNode;
  state: "done" | "current" | "pending" | "failed";
  action?: React.ReactNode;
};

/*
  A chain is a sequence, and a table does not say sequence. The spine carries
  the order, the node carries the state, and what is waiting on you is the only
  node that is filled.
*/
export function Timeline({ steps }: Readonly<{ steps: TimelineStep[] }>) {
  return (
    <ol className="space-y-0">
      {steps.map((step, index) => (
        <li key={step.id} className="relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-3">
          {index < steps.length - 1 ? (
            <span
              aria-hidden
              className={cn(
                "absolute left-[0.8125rem] top-7 w-px",
                "h-[calc(100%-1.25rem)]",
                step.state === "done" ? "bg-primary/45" : "bg-border",
              )}
            />
          ) : null}
          <span
            aria-hidden
            className={cn(
              "z-10 mt-0.5 flex h-7 w-7 items-center justify-center rounded-full border text-2xs font-semibold",
              step.state === "done" && "border-primary bg-primary text-primary-foreground",
              step.state === "current" && "border-brand bg-brand text-brand-foreground",
              step.state === "failed" && "border-destructive bg-destructive text-destructive-foreground",
              step.state === "pending" && "border-border bg-muted text-muted-foreground",
            )}
          >
            {step.state === "done" ? "\u2713" : step.state === "failed" ? "\u2715" : index + 1}
          </span>
          <div className="min-w-0 pb-6 last:pb-0">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <div
                className={cn(
                  "text-sm font-medium",
                  step.state === "pending" && "text-muted-foreground",
                  step.state === "current" && "text-brand",
                )}
              >
                {step.title}
              </div>
              {step.meta ? (
                <div className="text-xs text-muted-foreground">{step.meta}</div>
              ) : null}
            </div>
            {step.detail ? (
              <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
                {step.detail}
              </div>
            ) : null}
            {step.action ? <div className="mt-2.5">{step.action}</div> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

/*
  Two of three signatures is a fraction, and a fraction reads faster as an arc
  than as three rows you have to count.
*/
export function Ring({
  done,
  total,
  label,
  detail,
}: Readonly<{ done: number; total: number; label?: string; detail?: React.ReactNode }>) {
  const safeTotal = Math.max(total, 1);
  const fraction = Math.min(Math.max(done / safeTotal, 0), 1);
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const complete = done >= total && total > 0;

  return (
    <div className="flex items-center gap-4">
      <svg
        viewBox="0 0 64 64"
        className="h-16 w-16 shrink-0 -rotate-90"
        role="img"
        aria-label={`${done} of ${total}`}
      >
        <circle cx="32" cy="32" r={radius} fill="none" strokeWidth="6" className="stroke-muted" />
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${circumference * fraction} ${circumference}`}
          className={complete ? "stroke-primary" : "stroke-brand"}
        />
      </svg>
      <div className="min-w-0">
        <div className="text-lg font-semibold leading-tight">
          {done} of {total}
        </div>
        {label ? <div className="text-sm font-medium">{label}</div> : null}
        {detail ? <div className="mt-0.5 text-xs text-muted-foreground">{detail}</div> : null}
      </div>
    </div>
  );
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
  /*
    One wrapping row rather than a breakpoint. A screen with two actions and a
    screen with seven need the break at different widths, and picking a single
    one starved the title on the busy screens: the heading was squeezed to a
    column narrow enough to wrap its own identifier a character at a time. The
    title keeps a floor it cannot be compressed past, and the actions drop to
    their own line when what is left will not hold them.
  */
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div className="min-w-full flex-1 sm:min-w-[20rem]">
        <h1 className="text-2xl font-semibold tracking-tight text-heading sm:text-3xl">
          {title}
        </h1>
        {subtitle ? (
          <div className="mt-2 max-w-reading text-base leading-relaxed text-muted-foreground">
            {subtitle}
          </div>
        ) : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
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

/*
  The header offset is zero, not the height of the page header. Every table
  sits inside .table-scroll, and overflow-x: auto makes the browser compute
  overflow-y: auto with it, so that box is the scrollport a sticky child
  measures against. A 4rem offset there did not hold the header below the page
  header; it pushed the header 4rem below its own place in the table and let
  the first row show through the gap.
*/
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
          ? "sticky top-0 z-10 border-b bg-muted py-3 text-xs font-medium uppercase tracking-wide text-muted-foreground"
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

  /*
    Held in a ref, not a dependency. Every call site passes an inline arrow, so
    onClose is a new function on every render; depending on it re-ran this
    effect on every keystroke, and the focus call below moved the caret out of
    whatever was being typed into.
  */
  const closeRef = React.useRef(onClose);
  closeRef.current = onClose;

  React.useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open]);

  /*
    Focus is placed once, when the dialog opens, and on the first field rather
    than the first focusable node. In document order that node is the close
    control in the header, so focusing it put the caret on the dismiss button
    of a form somebody had just been asked to fill in.
  */
  React.useEffect(() => {
    if (!open) return;
    const field = panel.current?.querySelector<HTMLElement>(
      "input:not([type='hidden']), select, textarea",
    );
    (field ?? panel.current?.querySelector<HTMLElement>("button:not([data-dismiss])"))?.focus();
  }, [open]);

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
          <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close" data-dismiss>
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
