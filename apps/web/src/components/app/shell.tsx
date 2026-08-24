"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import { Icon, type IconName } from "@/components/app/icons";
import { Notifications } from "@/components/app/notifications";
import { Search } from "@/components/app/search";
import { useSession } from "@/components/app/session";
import { ThemeToggle } from "@/components/app/theme-toggle";
import { Button, Spinner } from "@/components/ui";
import { logout } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Me, NavCounts, SearchHit, SearchResults } from "@/lib/types";
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
  /*
    Which outstanding count belongs on this item. Only work waiting is
    counted, never a total: a screen holding 248 records tells nobody
    anything, and a screen holding 12 awaiting a decision tells them where
    to go next.
  */
  counter?: keyof NavCounts;
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
      {
        href: "/workspace/triage",
        icon: "triage",
        label: "Triage",
        module: "M02",
        roles: LEGAL,
        counter: "triage",
      },
      {
        href: "/workspace/matters",
        icon: "matters",
        label: "Matters",
        module: "M02",
        roles: LEGAL,
        counter: "matters",
      },
      {
        href: "/workspace/review",
        icon: "review",
        label: "Review",
        module: "M06",
        roles: LEGAL,
        counter: "review",
      },
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
        counter: "obligations",
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
      {
        href: "/workspace/inbox",
        icon: "inbox",
        label: "Inbox",
        module: "M09",
        roles: LEGAL,
        counter: "inbox",
      },
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
        counter: "assessments",
      },
      {
        href: "/workspace/compliance",
        icon: "compliance",
        label: "Compliance",
        module: "M12",
        roles: LEGAL,
        counter: "compliance",
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

const SIDEBAR_KEY = "dsn-lai-sidebar";

const ENTITY_NAMES: Record<string, string> = {
  DSN: "Data Science Nigeria",
  EAI: "EqualyzAI",
};

/*
  The organisation already tints the whole surface through the data-entity
  tokens in globals.css. That tint is deliberately faint, and faint colour is
  not a cue anyone should have to rely on, so the name carries a mark beside it
  in the organisation's own hue.

  These are fixed hues rather than --brand, because both organisations appear
  together in the switcher and --brand is whichever one you are already in.
  A menu where both rows are the same colour tells you nothing.
*/
const ENTITY_MARK: Record<string, string> = {
  DSN: "bg-info",
  EAI: "bg-primary",
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

/*
  A record belongs to one organisation, so switching organisation cannot leave
  it open. Row-level security would refuse the next read anyway and the screen
  would become a not-found; going back to the list the record came from says
  the same thing without looking like a fault.
*/
const LIST_ROUTES = new Set(NAV.flatMap((section) => section.items.map((item) => item.href)));

function listFor(pathname: string): string | null {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length <= 2) return null;
  const parent = `/${segments.slice(0, 2).join("/")}`;
  return LIST_ROUTES.has(parent) ? parent : "/workspace";
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

/*
  One component serves three shapes: the permanent rail, the collapsed rail and
  the mobile drawer. Collapsing hides the words, never the items, so the set of
  places a role can reach does not change with the width of the sidebar.

  The four bands are separate components because each one branches on
  `collapsed` in its own way, and reading four small branches beats reading one
  function that branches nine times.
*/
function EntityMark({ code, className }: Readonly<{ code: string; className?: string }>) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "h-1.5 w-1.5 shrink-0 rounded-full",
        ENTITY_MARK[code] ?? "bg-muted-foreground",
        className,
      )}
    />
  );
}

function SidebarBrand({
  entity,
  collapsed,
  onToggle,
}: Readonly<{ entity: string; collapsed: boolean; onToggle?: () => void }>) {
  return (
    <div
      className={cn("flex items-center gap-3 border-b py-4", collapsed ? "flex-col px-2" : "px-4")}
    >
      <Image
        src="/dsn-logo.png"
        alt=""
        width={34}
        height={34}
        /* Both dimensions in CSS as well as on the element. Tailwind's reset
           sets height:auto on every image, which changes one of the two and
           leaves the browser to guess the other. */
        className="h-[34px] w-[34px] shrink-0 rounded-sm"
      />
      {collapsed ? null : (
        <div className="min-w-0 flex-1">
          <div className="truncate text-[0.9375rem] font-semibold leading-tight">
            Legal Operations
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <EntityMark code={entity} />
            <span className="truncate">{ENTITY_NAMES[entity] ?? entity}</span>
          </div>
        </div>
      )}
      {onToggle ? (
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}
          title={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground"
        >
          <Icon name={collapsed ? "expand" : "collapse"} className="h-[1.15rem] w-[1.15rem]" />
        </button>
      ) : null}
    </div>
  );
}

function EntitySwitch({
  entities,
  entity,
  setEntity,
  collapsed,
}: Readonly<{
  entities: string[];
  entity: string;
  setEntity: (code: string) => void;
  collapsed: boolean;
}>) {
  if (entities.length <= 1) return null;

  return (
    <div className={cn("pt-3", collapsed ? "px-2" : "px-3")}>
      <fieldset
        className={cn(
          "rounded-md border bg-card/60 p-1",
          collapsed ? "flex flex-col gap-1" : "flex",
        )}
      >
        <legend className="sr-only">Entity</legend>
        {entities.map((code) => (
          <button
            key={code}
            onClick={() => setEntity(code)}
            aria-pressed={entity === code}
            aria-label={ENTITY_NAMES[code] ?? code}
            title={ENTITY_NAMES[code] ?? code}
            className={cn(
              "rounded-sm py-1.5 text-sm font-semibold transition-colors",
              collapsed ? "w-full" : "flex-1",
              entity === code
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <span className="flex items-center justify-center gap-1.5">
              <EntityMark
                code={code}
                className={cn("transition-opacity", entity === code ? "opacity-100" : "opacity-40")}
              />
              {collapsed ? null : code}
            </span>
          </button>
        ))}
      </fieldset>
    </div>
  );
}

function NavLink({
  item,
  active,
  collapsed,
  count,
  onNavigate,
}: Readonly<{
  item: NavItem;
  active: boolean;
  collapsed: boolean;
  count?: number;
  onNavigate: () => void;
}>) {
  const badge = count && count > 0 ? count : null;
  const hint = badge ? `${item.label}, ${badge} waiting` : item.label;
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      title={collapsed ? hint : `${hint}, ${item.module}`}
      aria-label={collapsed ? item.label : undefined}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex min-h-10 items-center rounded-md py-2 text-[0.9375rem] no-underline transition-colors",
        collapsed ? "justify-center px-0" : "gap-3 px-3",
        active
          ? "bg-heading/10 font-semibold text-heading"
          : "text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground",
      )}
    >
      <span className="relative shrink-0">
        <Icon
          name={item.icon}
          className={cn(
            "h-[1.15rem] w-[1.15rem]",
            active ? "text-heading" : "text-muted-foreground/70",
          )}
        />
        {collapsed && badge ? (
          <span
            aria-hidden
            className="absolute -right-1.5 -top-1.5 h-2 w-2 rounded-full bg-brand ring-2 ring-sidebar"
          />
        ) : null}
      </span>
      {collapsed ? null : (
        <>
          <span className="truncate">{item.label}</span>
          {badge ? (
            <span
              className={cn(
                "ml-auto min-w-[1.375rem] shrink-0 rounded-full px-1.5 py-0.5 text-center text-2xs font-semibold tabular-nums",
                active
                  ? "bg-heading text-background"
                  : "bg-foreground/[0.08] text-muted-foreground",
              )}
            >
              {badge > 99 ? "99+" : badge}
            </span>
          ) : null}
        </>
      )}
    </Link>
  );
}

function SidebarNav({
  sections,
  pathname,
  collapsed,
  counts,
  onNavigate,
}: Readonly<{
  sections: { group: string; items: NavItem[] }[];
  pathname: string;
  collapsed: boolean;
  counts: NavCounts | null;
  onNavigate: () => void;
}>) {
  return (
    <nav
      className={cn("flex-1 overflow-y-auto py-3", collapsed ? "px-2" : "px-3")}
      aria-label="Workspace"
    >
      {sections.map((section) => (
        <div key={section.group} className="mb-5 last:mb-0">
          {collapsed ? (
            <div className="mx-2 mb-2 border-t" />
          ) : (
            <div className="px-3 pb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-heading">
              {section.group}
            </div>
          )}
          <div className="space-y-0.5">
            {section.items.map((item) => (
              <NavLink
                key={item.href}
                item={item}
                active={isActive(pathname, item.href)}
                collapsed={collapsed}
                count={item.counter && counts ? counts[item.counter] : undefined}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}

function SidebarFooter({ me, collapsed }: Readonly<{ me: Me; collapsed: boolean }>) {
  const role = primaryRole(me.roles);

  return (
    <div className={cn("border-t py-3", collapsed ? "px-2" : "px-3")}>
      <Link
        href="/portal"
        title="Open the requester portal"
        className="mb-3 block rounded-md border px-3 py-2 text-center text-sm text-muted-foreground no-underline transition-colors hover:bg-foreground/[0.06] hover:text-foreground"
      >
        {collapsed ? (
          <Icon name="inbox" className="mx-auto h-[1.15rem] w-[1.15rem]" />
        ) : (
          "Open the requester portal"
        )}
      </Link>
      <div className={cn("flex items-center gap-3", collapsed && "justify-center")}>
        <span
          title={collapsed ? `${me.name}, ${role}` : undefined}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-semibold text-brand-foreground"
        >
          {initials(me.name)}
        </span>
        {collapsed ? null : (
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{me.name}</div>
            <div className="truncate text-xs text-muted-foreground">{role}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function Sidebar({
  me,
  entity,
  setEntity,
  pathname,
  collapsed,
  onToggle,
  counts,
  onNavigate,
}: Readonly<{
  me: Me;
  entity: string;
  setEntity: (code: string) => void;
  pathname: string;
  collapsed: boolean;
  counts: NavCounts | null;
  onToggle?: () => void;
  onNavigate: () => void;
}>) {
  return (
    <div className="flex h-full flex-col bg-sidebar">
      <SidebarBrand entity={entity} collapsed={collapsed} onToggle={onToggle} />
      <EntitySwitch
        entities={me.entities}
        entity={entity}
        setEntity={setEntity}
        collapsed={collapsed}
      />
      <SidebarNav
        sections={visibleNav(me.roles)}
        pathname={pathname}
        collapsed={collapsed}
        counts={counts}
        onNavigate={onNavigate}
      />
      <SidebarFooter me={me} collapsed={collapsed} />
    </div>
  );
}

export function Shell({ children }: Readonly<{ children: React.ReactNode }>) {
  const { me, status, error, entity, setEntity, refresh } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);

  /*
    Read once on mount rather than during render, because the server has no
    storage to read and a mismatch would be a hydration error.
  */
  React.useEffect(() => {
    try {
      setCollapsed(globalThis.localStorage.getItem(SIDEBAR_KEY) === "collapsed");
    } catch {
      setCollapsed(false);
    }
  }, []);

  const switchEntity = React.useCallback(
    (code: string) => {
      if (code === entity) return;
      setEntity(code);
      const list = listFor(pathname);
      if (list) router.replace(list);
    },
    [entity, setEntity, pathname, router],
  );

  const toggleSidebar = React.useCallback(() => {
    setCollapsed((previous) => {
      const next = !previous;
      try {
        globalThis.localStorage.setItem(SIDEBAR_KEY, next ? "collapsed" : "expanded");
      } catch {
        // A browser that refuses storage still gets the toggle, just not the memory of it.
      }
      return next;
    });
  }, []);

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

  /*
    Reloaded on every navigation as well as on an entity switch, because a
    badge that is stale after you clear the queue it counted is worse than no
    badge. A refusal leaves the counts absent rather than showing zero, since
    zero is a claim that there is no work.
  */
  const counts = useApi<NavCounts>("/workspace/counts", [entity, pathname]);

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
      <aside
        className={cn(
          "hidden shrink-0 border-r transition-[width] duration-200 lg:block",
          collapsed ? "w-[4.25rem]" : "w-[17rem] xl:w-[18.5rem]",
        )}
      >
        <div className="sticky top-0 h-screen">
          <Sidebar
            me={me}
            entity={entity}
            setEntity={switchEntity}
            pathname={pathname}
            collapsed={collapsed}
            counts={counts.data ?? null}
            onToggle={toggleSidebar}
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
              setEntity={switchEntity}
              pathname={pathname}
              collapsed={false}
              counts={counts.data ?? null}
              onNavigate={() => setDrawerOpen(false)}
            />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-3 border-b bg-card px-4 sm:px-6">
          <div className="flex min-w-0 flex-1 items-center gap-3">
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
            <div className="min-w-0 shrink-0 truncate text-sm">
              <span className="font-semibold text-heading">{entity}</span>
              <span className="mx-2 hidden text-border lg:inline">/</span>
              <span className="hidden text-muted-foreground lg:inline">
                {currentLabel(pathname)}
              </span>
            </div>
            <div className="hidden min-w-0 flex-1 md:block">
              <Search entity={entity} />
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            <span className="hidden rounded-md border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground md:inline">
              {primaryRole(me.roles)}
            </span>
            <Notifications entity={entity} />
            <ThemeToggle />
            <Button
              size="sm"
              variant="destructive"
              onClick={() => {
                logout();
                router.replace("/sign-in");
              }}
            >
              <Icon name="signout" className="h-4 w-4" />
              <span className="hidden sm:inline">Sign out</span>
              <span className="sr-only sm:hidden">Sign out</span>
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
