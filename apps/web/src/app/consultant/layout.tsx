import Image from "next/image";

import { SessionProvider } from "@/components/app/session";
import { ThemeToggle } from "@/components/app/theme-toggle";

import { ConsultantNav } from "./nav";

/*
  External counsel gets its own shell.

  Not the workspace, because a consultant is not staff and the workspace is a
  place to run a legal department. Not the portal either, because they are not
  raising requests. One page, holding the matters they were actually asked
  about, and nothing else: the navigation has nowhere else to offer because
  there is nowhere else they may go.
*/
export default function ConsultantLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <SessionProvider>
      <div className="min-h-screen">
        <header className="border-b bg-card">
          <div className="mx-auto flex h-16 w-full max-w-5xl items-center gap-3 px-4 sm:px-6">
            <Image
              src="/dsn-logo.png"
              alt=""
              width={32}
              height={32}
              className="h-8 w-8 rounded-sm"
            />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">Counsel review</div>
              <div className="truncate text-xs text-muted-foreground">
                Data Science Nigeria and EqualyzAI
              </div>
            </div>
            <ConsultantNav />
            <ThemeToggle />
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      </div>
    </SessionProvider>
  );
}
