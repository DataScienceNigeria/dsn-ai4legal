import Image from "next/image";
import Link from "next/link";

import { SessionProvider } from "@/components/app/session";
import { ThemeToggle } from "@/components/app/theme-toggle";

export default function PortalLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <SessionProvider>
      <div className="min-h-screen">
        <header className="border-b bg-card">
          <div className="mx-auto flex h-16 w-full max-w-3xl items-center gap-3 px-4 sm:px-6">
            <Image src="/dsn-logo.png" alt="" width={32} height={32} className="rounded-sm" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">Legal requests</div>
              <div className="truncate text-xs text-muted-foreground">
                Data Science Nigeria and EqualyzAI
              </div>
            </div>
            <Link
              href="/portal/status"
              className="whitespace-nowrap text-sm text-muted-foreground no-underline hover:text-foreground"
            >
              My requests
            </Link>
            <ThemeToggle />
          </div>
        </header>
        <main className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-10">{children}</main>
      </div>
    </SessionProvider>
  );
}
