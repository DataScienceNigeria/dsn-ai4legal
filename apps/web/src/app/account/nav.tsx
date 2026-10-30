"use client";

import Link from "next/link";

import { Icon } from "@/components/app/icons";
import { useSession } from "@/components/app/session";
import { SignOutButton } from "@/components/app/sign-out";
import { homeFor } from "@/lib/api";

/*
  The way back to wherever this account belongs, and the way out. Back is
  withheld while the password still has to be changed, because the place it
  leads would refuse every screen.
*/
export function AccountNav() {
  const { me } = useSession();

  return (
    <div className="flex items-center gap-2 sm:gap-3">
      {me && !me.password_must_change ? (
        <Link
          href={homeFor(me.roles)}
          className="rounded-md border px-3 py-1.5 text-sm text-muted-foreground no-underline transition-colors hover:bg-foreground/[0.06] hover:text-foreground"
        >
          <span className="hidden sm:inline">Back to the platform</span>
          <span className="sm:hidden">Back</span>
        </Link>
      ) : null}
      <SignOutButton size="sm" variant="destructive">
        <Icon name="signout" className="h-4 w-4" />
        <span className="hidden sm:inline">Sign out</span>
        <span className="sr-only sm:hidden">Sign out</span>
      </SignOutButton>
    </div>
  );
}
