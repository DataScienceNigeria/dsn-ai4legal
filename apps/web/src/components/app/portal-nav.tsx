"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import { Icon } from "@/components/app/icons";
import { useSession } from "@/components/app/session";
import { Button } from "@/components/ui";
import { logout } from "@/lib/api";
import { cn } from "@/lib/utils";

/*
  The portal is a place people arrive at, finish something and leave. Every one
  of those exits has to be on the page: back to the workspace for anyone who
  has one, and a sign-out for anyone who does not, because a requester who has
  finished should not have to close the tab to leave.
*/
const WORKSPACE_ROLES = new Set([
  "counsel",
  "head_of_legal",
  "admin",
  "auditor",
  "privacy",
  "management",
]);

/*
  What a department lead does here.

  They are not legal staff, so nothing in this rail reaches the workspace. Each
  entry is somewhere they can actually go, which is the whole test a navigation
  has to pass: an item that leads to a refusal is worse than no item.
*/
const SIDE_LINKS = [
  {
    href: "/portal",
    icon: "plus" as const,
    label: "Raise a request",
    detail: "Contracts, advice, anything legal",
  },
  {
    href: "/portal/status",
    icon: "matters" as const,
    label: "My requests",
    detail: "What you have asked for, and where it is",
  },
  {
    href: "/portal/assessments",
    icon: "assessments" as const,
    label: "Data protection",
    detail: "Assessments for what your team builds",
  },
];

export function PortalNav() {
  const { me } = useSession();
  const pathname = usePathname();
  const router = useRouter();

  const hasWorkspace = (me?.roles ?? []).some((role) => WORKSPACE_ROLES.has(role));

  return (
    <nav className="flex items-center gap-1 sm:gap-2" aria-label="Portal">
      {me?.name ? (
        <span className="hidden text-sm text-muted-foreground sm:inline">{me.name}</span>
      ) : null}

      {hasWorkspace ? (
        <Link
          href="/workspace"
          title="Back to the workspace"
          className="whitespace-nowrap rounded-md border px-2.5 py-1.5 text-sm text-muted-foreground no-underline transition-colors hover:bg-foreground/[0.06] hover:text-foreground"
        >
          <span className="hidden sm:inline">Back to my workspace</span>
          <span className="sm:hidden">Workspace</span>
        </Link>
      ) : null}

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
    </nav>
  );
}


/*
  The rail. On a narrow screen it becomes a row above the content rather than
  disappearing behind a control: three destinations fit across a phone, and a
  menu that has to be opened to find out what is in it is a menu nobody opens.
*/
export function PortalSideNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Portal sections"
      className="w-full shrink-0 lg:w-60"
    >
      <ul className="flex gap-1.5 overflow-x-auto pb-1 lg:sticky lg:top-6 lg:flex-col lg:gap-1 lg:overflow-visible lg:pb-0">
        {SIDE_LINKS.map((link) => {
          const active =
            pathname === link.href ||
            (link.href !== "/portal" && pathname.startsWith(`${link.href}/`));
          return (
            <li key={link.href} className="min-w-0">
              <Link
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-start gap-2.5 whitespace-nowrap rounded-lg px-3 py-2.5 no-underline transition-colors lg:whitespace-normal",
                  active
                    ? "bg-heading/10 text-heading"
                    : "text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground",
                )}
              >
                <Icon name={link.icon} className="mt-0.5 h-4 w-4 shrink-0" />
                <span className="min-w-0">
                  <span className={cn("block text-sm", active && "font-medium")}>
                    {link.label}
                  </span>
                  <span className="hidden text-xs leading-snug text-muted-foreground lg:block">
                    {link.detail}
                  </span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
