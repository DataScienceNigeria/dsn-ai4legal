import * as React from "react";

/*
  Inline rather than a dependency. Two dozen glyphs do not justify an icon
  package in a build that has to be auditable, and drawing them here keeps
  stroke weight and optical size consistent with the type scale.

  Every icon is decorative. The navigation label carries the meaning, so each
  is hidden from assistive technology.
*/

export type IconName =
  | "delivery"
  | "triage"
  | "matters"
  | "review"
  | "archive"
  | "obligations"
  | "templates"
  | "memory"
  | "inbox"
  | "assessments"
  | "compliance"
  | "counterparties"
  | "metrics"
  | "capabilities"
  | "administration"
  | "signout"
  | "collapse"
  | "expand"
  | "chat"
  | "plus"
  | "send"
  | "trash"
  | "rename"
  | "stop";

const PATHS: Record<IconName, React.ReactNode> = {
  delivery: (
    <>
      <path d="M3 13.5 10 6l4 4 7-7" />
      <path d="M21 3v6h-6" />
      <path d="M3 21h18" />
    </>
  ),
  triage: (
    <>
      <path d="M3 5h18" />
      <path d="M6 12h12" />
      <path d="M10 19h4" />
    </>
  ),
  matters: (
    <>
      <path d="M4 6a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" />
      <path d="M4 10h16" />
    </>
  ),
  review: (
    <>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
      <path d="M14 3v5h5" />
      <path d="m9 14 2 2 4-4" />
    </>
  ),
  archive: (
    <>
      <path d="M3 5h18v4H3Z" />
      <path d="M5 9v10h14V9" />
      <path d="M10 13h4" />
    </>
  ),
  obligations: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  templates: (
    <>
      <path d="M4 4h16v16H4Z" />
      <path d="M4 9h16" />
      <path d="M9 9v11" />
    </>
  ),
  memory: (
    <>
      <path d="M21 12a8 8 0 1 1-3.2-6.4" />
      <path d="M4 19l1.4-3.6" />
      <path d="M12 8v4.5l3 1.5" />
    </>
  ),
  inbox: (
    <>
      <path d="M3 12h5l2 3h4l2-3h5" />
      <path d="M4.5 6h15l1.5 6v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5Z" />
    </>
  ),
  assessments: (
    <>
      <path d="M12 3.5 20 7v5.5c0 4.3-3.3 7.4-8 8.5-4.7-1.1-8-4.2-8-8.5V7Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  compliance: (
    <>
      <path d="M5 4h14v17l-7-3-7 3Z" />
      <path d="M9 9h6" />
      <path d="M9 13h6" />
    </>
  ),
  counterparties: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
      <circle cx="17.5" cy="9.5" r="2.5" />
      <path d="M15 16.5a4.5 4.5 0 0 1 6 0" />
    </>
  ),
  metrics: (
    <>
      <path d="M4 20V10" />
      <path d="M10 20V4" />
      <path d="M16 20v-7" />
      <path d="M22 20H2" />
    </>
  ),
  capabilities: (
    <>
      <path d="M12 3v3" />
      <path d="M12 18v3" />
      <path d="M3 12h3" />
      <path d="M18 12h3" />
      <circle cx="12" cy="12" r="4" />
      <path d="m5.6 5.6 2.1 2.1" />
      <path d="m16.3 16.3 2.1 2.1" />
    </>
  ),
  administration: (
    <>
      <path d="M4 7h16" />
      <path d="M4 12h16" />
      <path d="M4 17h16" />
      <circle cx="9" cy="7" r="1.8" />
      <circle cx="15" cy="12" r="1.8" />
      <circle cx="8" cy="17" r="1.8" />
    </>
  ),
  signout: (
    <>
      <path d="M15 17l5-5-5-5" />
      <path d="M20 12H9" />
      <path d="M12 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h6" />
    </>
  ),
  collapse: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M10 4v16" />
      <path d="M17 9l-2.5 3 2.5 3" />
    </>
  ),
  expand: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M10 4v16" />
      <path d="M14 9l2.5 3-2.5 3" />
    </>
  ),
  chat: <path d="M21 12a8 8 0 0 1-8 8H7l-4 3v-6.5A8 8 0 0 1 11 4h2a8 8 0 0 1 8 8Z" />,
  plus: (
    <>
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </>
  ),
  send: (
    <>
      <path d="M4 12 20 4l-4 16-4.5-6.5L4 12Z" />
      <path d="m11.5 13.5 8.5-9.5" />
    </>
  ),
  trash: (
    <>
      <path d="M4 7h16" />
      <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
      <path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" />
    </>
  ),
  rename: (
    <>
      <path d="M4 20h4l10-10a2.8 2.8 0 0 0-4-4L4 16v4Z" />
      <path d="m13.5 6.5 4 4" />
    </>
  ),
  stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
};

export function Icon({
  name,
  className,
}: Readonly<{ name: IconName; className?: string }>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {PATHS[name]}
    </svg>
  );
}
