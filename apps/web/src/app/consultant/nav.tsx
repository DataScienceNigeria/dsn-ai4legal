"use client";

import Link from "next/link";
import { Icon } from "@/components/app/icons";
import { useSession } from "@/components/app/session";
import { SignOutButton } from "@/components/app/sign-out";

/*
  Who is signed in, and the way out.

  External counsel is the account most likely to be open on somebody else's
  machine, in a chambers shared between clients, and it is the one account the
  organisation cannot ask to close a tab. A shell with no sign-out was the wrong
  one to leave it off.
*/
export function ConsultantNav() {
  const { me } = useSession();

  return (
    <div className="flex items-center gap-2 sm:gap-3">
      {me?.name ? (
        <span className="hidden text-sm text-muted-foreground sm:inline">{me.name}</span>
      ) : null}
      <Link
        href="/account"
        title="Account settings"
        className="whitespace-nowrap rounded-md border px-2.5 py-1.5 text-sm text-muted-foreground no-underline transition-colors hover:bg-foreground/[0.06] hover:text-foreground"
      >
        <span className="hidden sm:inline">Account</span>
        <span className="sr-only sm:hidden">Account settings</span>
        <Icon name="key" className="h-4 w-4 sm:hidden" />
      </Link>
      <SignOutButton size="sm" variant="destructive">
        <Icon name="signout" className="h-4 w-4" />
        <span className="hidden sm:inline">Sign out</span>
        <span className="sr-only sm:hidden">Sign out</span>
      </SignOutButton>
    </div>
  );
}
