import Image from "next/image";

import { PortalNav } from "@/components/app/portal-nav";
import { SessionProvider } from "@/components/app/session";
import { ThemeToggle } from "@/components/app/theme-toggle";

export default function PortalLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <SessionProvider>
      <div className="min-h-screen">
        <header className="border-b bg-card">
          <div className="mx-auto flex h-16 w-full max-w-4xl items-center gap-3 px-4 sm:px-6">
            <Image src="/dsn-logo.png" alt="" width={32} height={32} className="h-8 w-8 rounded-sm" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">Legal requests</div>
              <div className="truncate text-xs text-muted-foreground">
                Data Science Nigeria and EqualyzAI
              </div>
            </div>
            <PortalNav />
            <ThemeToggle />
          </div>
        </header>
        <main className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-10">{children}</main>
      </div>
    </SessionProvider>
  );
}
