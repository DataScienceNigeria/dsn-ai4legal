import Image from "next/image";

import { PortalNav, PortalSideNav } from "@/components/app/portal-nav";
import { SessionProvider } from "@/components/app/session";
import { ThemeToggle } from "@/components/app/theme-toggle";

/*
  The portal grew a side rail.

  It was built for one errand: raise a request, leave. Requesters turned out to
  be the team leads of other departments, who come back, who have several
  things in flight, and who now also write the data protection assessment for
  anything their team builds. Two links across the top could carry the errand;
  they cannot carry a place somebody works.

  The rail is theirs and stops at what they may do. Nothing in it reaches the
  legal workspace: a department lead is not legal staff, and a navigation that
  offers them a door they cannot open is a navigation that lies.
*/
export default function PortalLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <SessionProvider>
      <div className="min-h-screen">
        <header className="border-b bg-card">
          <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-4 sm:px-6">
            <Image
              src="/dsn-logo.png"
              alt=""
              width={32}
              height={32}
              className="h-8 w-8 rounded-sm"
            />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">Legal and privacy</div>
              <div className="truncate text-xs text-muted-foreground">
                Data Science Nigeria and EqualyzAI
              </div>
            </div>
            <PortalNav />
            <ThemeToggle />
          </div>
        </header>

        <div className="mx-auto flex w-full max-w-6xl gap-6 px-4 py-6 sm:px-6 sm:py-8 lg:gap-8">
          <PortalSideNav />
          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </div>
    </SessionProvider>
  );
}
