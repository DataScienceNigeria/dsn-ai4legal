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
  "legal_ops",
  "counsel",
  "head_of_legal",
  "admin",
  "auditor",
  "privacy",
  "management",
]);

const LINKS = [
  { href: "/portal", label: "Raise a request" },
  { href: "/portal/status", label: "My requests" },
];

export function PortalNav() {
  const { me } = useSession();
  const pathname = usePathname();
  const router = useRouter();

  const hasWorkspace = (me?.roles ?? []).some((role) => WORKSPACE_ROLES.has(role));

  return (
    <nav className="flex items-center gap-1 sm:gap-2" aria-label="Portal">
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          aria-current={pathname === link.href ? "page" : undefined}
          className={cn(
            "whitespace-nowrap rounded-md px-2 py-1.5 text-sm no-underline transition-colors sm:px-2.5",
            pathname === link.href
              ? "bg-heading/10 font-medium text-heading"
              : "text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground",
          )}
        >
          {link.label}
        </Link>
      ))}

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
