"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import { Icon, type IconName } from "@/components/app/icons";
import { useSession } from "@/components/app/session";
import { ThemeToggle } from "@/components/app/theme-toggle";
import { Button, Spinner } from "@/components/ui";
import { logout } from "@/lib/api";
import type { Me } from "@/lib/types";
import { cn, initials, titleCase } from "@/lib/utils";

/*
  The roles on each item mirror the require_role call on the endpoint behind
  it. Navigation offers a screen only where the API would answer, so a role
  meets an absent link rather than a refusal it could not have predicted.
*/
type NavItem = {
  href: string;
  icon: IconName;
  label: string;
  module: string;
  roles: string[];
};

const LEGAL = ["legal_ops", "counsel", "head_of_legal", "admin"];

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "The work",
    items: [
      {
        href: "/workspace",
        icon: "delivery",
        label: "Delivery",
        module: "M14",
        roles: [...LEGAL, "management"],
      },
      { href: "/workspace/triage", icon: "triage", label: "Triage", module: "M02", roles: LEGAL },
      { href: "/workspace/matters", icon: "matters", label: "Matters", module: "M02", roles: LEGAL },
      { href: "/workspace/review", icon: "review", label: "Review", module: "M06", roles: LEGAL },
      {
        href: "/workspace/archive",
        icon: "archive",
        label: "Archive",
        module: "M08",
        roles: [...LEGAL, "auditor"],
      },
      {
        href: "/workspace/obligations",
        icon: "obligations",
        label: "Obligations",
        module: "M08",
        roles: LEGAL,
      },
    ],
  },
  {
    group: "Knowledge",
    items: [
      {
        href: "/workspace/library",
        icon: "templates",
        label: "Templates",
        module: "M03",
        roles: LEGAL,
      },
      { href: "/workspace/memory", icon: "memory", label: "Memory", module: "M10", roles: LEGAL },
      { href: "/workspace/inbox", icon: "inbox", label: "Inbox", module: "M09", roles: LEGAL },
    ],
  },
  {
    group: "Governance",
    items: [
      {
        href: "/workspace/assessments",
        icon: "assessments",
        label: "Assessments",
        module: "M11",
        roles: [...LEGAL, "privacy"],
      },
      {
        href: "/workspace/compliance",
        icon: "compliance",
        label: "Compliance",
        module: "M12",
        roles: LEGAL,
      },
      {
        href: "/workspace/counterparties",
        icon: "counterparties",
        label: "Counterparties",
        module: "M13",
        roles: [...LEGAL, "privacy"],
      },
    ],
  },
  {
    group: "Platform",
    items: [
      {
        href: "/workspace/metrics",
        icon: "metrics",
        label: "Metrics",
        module: "M14",
        roles: ["head_of_legal", "management", "admin", "auditor", "counsel"],
      },
      {
        href: "/workspace/capabilities",
        icon: "capabilities",
        label: "Capabilities",
        module: "M15",
        roles: ["admin", "head_of_legal", "auditor", "counsel", "privacy"],
      },
      {
        href: "/workspace/admin",
        icon: "administration",
        label: "Administration",
        module: "M15",
        roles: ["admin", "head_of_legal", "auditor"],
      },
    ],
  },
];

const ENTITY_NAMES: Record<string, string> = {
  DSN: "Data Science Nigeria",
  EAI: "EqualyzAI",
};

const ROLE_LABELS: Record<string, string> = {
  requester: "Requester",
  management: "Management",
  legal_ops: "Legal operations",
  counsel: "Counsel",
  head_of_legal: "Head of Legal",
  privacy: "Privacy, the DPO",
  admin: "Administrator",
  auditor: "Auditor",
  counterparty: "Counterparty",
};

function permitted(roles: string[], item: NavItem): boolean {
  return item.roles.some((role) => roles.includes(role));
}

function visibleNav(roles: string[]) {
  return NAV.map((section) => ({
    group: section.group,
    items: section.items.filter((item) => permitted(roles, item)),
  })).filter((section) => section.items.length > 0);
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/workspace") return pathname === "/workspace";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function currentLabel(pathname: string): string {
  for (const section of NAV) {
    for (const item of section.items) {
      if (isActive(pathname, item.href)) return item.label;
    }
  }
  return "Workspace";
}

function primaryRole(roles: string[]): string {
  const order = [
    "head_of_legal",
    "admin",
    "counsel",
    "privacy",
    "legal_ops",
    "auditor",
    "management",
    "requester",
  ];
  const found = order.find((role) => roles.includes(role));
  return found ? ROLE_LABELS[found] : titleCase(roles[0] ?? "user");
}

function Sidebar({
  me,
  entity,
  setEntity,
  pathname,
  onNavigate,
}: Readonly<{
  me: Me;
  entity: string;
  setEntity: (code: string) => void;
  pathname: string;
  onNavigate: () => void;
}>) {
  const sections = visibleNav(me.roles);

  return (
    <div className="flex h-full flex-col bg-card">
      <div className="flex items-center gap-3 border-b px-4 py-4">
        <Image src="/dsn-logo.png" alt="" width={34} height={34} className="rounded-sm" />
        <div className="min-w-0">
          <div className="truncate text-[0.9375rem] font-semibold leading-tight">
            Legal Operations
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {ENTITY_NAMES[entity] ?? entity}
          </div>
        </div>
      </div>

      {me.entities.length > 1 ? (
        <div className="px-3 pt-3">
          <fieldset className="flex rounded-md bg-muted p-1">
            <legend className="sr-only">Entity</legend>
            {me.entities.map((code) => (
              <button
                key={code}
                onClick={() => setEntity(code)}
                aria-pressed={entity === code}
                className={cn(
                  "flex-1 rounded-sm py-1.5 text-sm font-semibold transition-colors",
                  entity === code
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {code}
              </button>
            ))}
          </fieldset>
        </div>
      ) : null}

      <nav className="flex-1 overflow-y-auto px-3 py-3" aria-label="Workspace">
        {sections.map((section) => (
          <div key={section.group} className="mb-5 last:mb-0">
            <div className="px-3 pb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-muted-foreground/70">
              {section.group}
            </div>
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onNavigate}
                    title={`${item.label}, ${item.module}`}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex min-h-10 items-center gap-3 rounded-md px-3 py-2 text-[0.9375rem] no-underline transition-colors",
                      active
                        ? "bg-secondary/12 font-semibold text-secondary"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <Icon
                      name={item.icon}
                      className={cn(
                        "h-[1.15rem] w-[1.15rem] shrink-0",
                        active ? "text-secondary" : "text-muted-foreground/70",
                      )}
                    />
                    <span className="truncate">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t px-3 py-3">
        <Link
          href="/portal"
          className="mb-3 block rounded-md border px-3 py-2 text-center text-sm text-muted-foreground no-underline hover:bg-muted hover:text-foreground"
        >
          Open the requester portal
        </Link>
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-secondary text-sm font-semibold text-secondary-foreground">
            {initials(me.name)}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{me.name}</div>
            <div className="truncate text-xs text-muted-foreground">{primaryRole(me.roles)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Shell({ children }: Readonly<{ children: React.ReactNode }>) {
  const { me, status, error, entity, setEntity, refresh } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  React.useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  React.useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  const sections = me ? visibleNav(me.roles) : [];

  React.useEffect(() => {
    if (me && sections.length === 0) router.replace("/portal");
  }, [me, sections.length, router]);

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Opening the workspace" />
      </div>
    );
  }

  if (status === "unreachable") {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-lg rounded-lg border border-destructive/30 bg-destructive/5 p-5 sm:p-6">
          <div className="text-base font-semibold text-destructive">
            The workspace cannot reach the API
          </div>
          <p className="mt-2 text-sm leading-relaxed">{error}</p>
          <p className="mt-2 text-xs text-muted-foreground">
            It is expected at {process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="primary" onClick={() => void refresh()}>
              Try again
            </Button>
            <Button onClick={() => router.replace("/sign-in")}>Sign in</Button>
          </div>
        </div>
      </div>
    );
  }

  if (!me) return null;

  if (sections.length === 0) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-lg rounded-lg border bg-card p-6">
          <div className="text-base font-semibold">The workspace is not for your role</div>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {primaryRole(me.roles)} accounts raise requests and follow their own status through
            the portal. Taking you there now.
          </p>
          <div className="mt-4">
            <Button variant="primary" onClick={() => router.replace("/portal")}>
              Open the portal
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <a
        href="#workspace-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:border focus:bg-card focus:px-3 focus:py-2 focus:text-sm"
      >
        Skip to the content
      </a>
      <aside className="hidden w-[17rem] shrink-0 border-r lg:block xl:w-[18.5rem]">
        <div className="sticky top-0 h-screen">
          <Sidebar
            me={me}
            entity={entity}
            setEntity={setEntity}
            pathname={pathname}
            onNavigate={() => undefined}
          />
        </div>
      </aside>

      {drawerOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close the menu"
            className="absolute inset-0 bg-foreground/40"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-[18rem] max-w-[85vw] border-r shadow-xl">
            <Sidebar
              me={me}
              entity={entity}
              setEntity={setEntity}
              pathname={pathname}
              onNavigate={() => setDrawerOpen(false)}
            />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-3 border-b bg-card px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              className="lg:hidden"
              aria-label="Open the menu"
              aria-expanded={drawerOpen}
              onClick={() => setDrawerOpen(true)}
            >
              <span aria-hidden className="text-lg leading-none">
                &#9776;
              </span>
            </Button>
            <div className="min-w-0 truncate text-sm">
              <span className="font-semibold text-foreground">{entity}</span>
              <span className="hidden text-muted-foreground sm:inline"> workspace</span>
              <span className="mx-2 hidden text-border sm:inline">/</span>
              <span className="hidden text-muted-foreground sm:inline">
                {currentLabel(pathname)}
              </span>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            <span className="hidden rounded-md border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground md:inline">
              {primaryRole(me.roles)}
            </span>
            <ThemeToggle />
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                logout();
                router.replace("/sign-in");
              }}
            >
              Sign out
            </Button>
          </div>
        </header>
        <main id="workspace-content" className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-workspace">{children}</div>
        </main>
      </div>
    </div>
  );
}
