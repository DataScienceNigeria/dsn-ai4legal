import Image from "next/image";

import { SessionProvider } from "@/components/app/session";
import { ThemeToggle } from "@/components/app/theme-toggle";

import { AccountNav } from "./nav";

/*
  Your own account, outside the workspace and the portal. Everybody has one,
  requesters and external counsel included, and an account still holding an
  administrator's password is sent here before anywhere else, when neither of
  the other shells would let it load a screen.
*/
export default function AccountLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <SessionProvider>
      <div className="min-h-screen">
        <header className="border-b bg-card">
          <div className="mx-auto flex h-16 w-full max-w-3xl items-center gap-3 px-4 sm:px-6">
            <Image src="/dsn-logo.png" alt="" width={32} height={32} className="h-8 w-8 rounded-sm" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">Your account</div>
              <div className="truncate text-xs text-muted-foreground">
                Data Science Nigeria and EqualyzAI
              </div>
            </div>
            <AccountNav />
            <ThemeToggle />
          </div>
        </header>
        <main className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      </div>
    </SessionProvider>
  );
}
