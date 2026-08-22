import { SessionProvider } from "@/components/app/session";
import { Shell } from "@/components/app/shell";

export default function WorkspaceLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <SessionProvider>
      <Shell>{children}</Shell>
    </SessionProvider>
  );
}
