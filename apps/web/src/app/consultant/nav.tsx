"use client";

import { useRouter } from "next/navigation";

import { Icon } from "@/components/app/icons";
import { useSession } from "@/components/app/session";
import { Button } from "@/components/ui";
import { logout } from "@/lib/api";

/*
  Who is signed in, and the way out.

  External counsel is the account most likely to be open on somebody else's
  machine, in a chambers shared between clients, and it is the one account the
  organisation cannot ask to close a tab. A shell with no sign-out was the wrong
  one to leave it off.
*/
export function ConsultantNav() {
  const { me } = useSession();
  const router = useRouter();

  return (
    <div className="flex items-center gap-2 sm:gap-3">
      {me?.name ? (
        <span className="hidden text-sm text-muted-foreground sm:inline">{me.name}</span>
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
    </div>
  );
}
