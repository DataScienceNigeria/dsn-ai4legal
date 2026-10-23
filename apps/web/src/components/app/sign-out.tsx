"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { Button, Confirm } from "@/components/ui";
import { logout } from "@/lib/api";

/*
  Every way out of the platform. The button sits beside things people click
  often, so leaving is confirmed first: a stray click should not cost somebody
  the draft they were half way through.
*/
export function SignOutButton(props: Readonly<React.ComponentProps<typeof Button>>) {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);

  return (
    <>
      <Button {...props} onClick={() => setOpen(true)} />
      <Confirm
        open={open}
        title="Sign out?"
        detail="Anything you have not saved on this page will be lost."
        confirmLabel="Sign out"
        destructive
        onCancel={() => setOpen(false)}
        onConfirm={() => {
          logout();
          router.replace("/sign-in");
        }}
      />
    </>
  );
}
