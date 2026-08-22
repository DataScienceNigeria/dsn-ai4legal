"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button, Card, CardBody, Field, Input, Notice } from "@/components/ui";
import { ApiError, login } from "@/lib/api";

const DEMO_ACCOUNTS = [
  { email: "adaeze.okafor@dsn.example", role: "Head of Legal, sees both entities" },
  { email: "ifeoma.chukwu@dsn.example", role: "Counsel" },
  { email: "amaka.eze@dsn.example", role: "Legal operations" },
  { email: "ngozi.adeyemi@dsn.example", role: "Requester, portal only" },
  { email: "emeka.obi@dsn.example", role: "AI and platform administrator" },
];

export default function SignIn() {
  const router = useRouter();
  const [email, setEmail] = React.useState("adaeze.okafor@dsn.example");
  const [password, setPassword] = React.useState("Lop-Demo-2026");
  const [code, setCode] = React.useState("");
  const [needsCode, setNeedsCode] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const destination = await login(email, password, code);
      router.replace(destination);
    } catch (exception) {
      // A missing second factor is not a failed sign-in. The form asks for
      // the code and keeps everything already typed.
      if (exception instanceof ApiError && exception.fieldErrors.code) {
        setNeedsCode(true);
        setError(exception.fieldErrors.code);
      } else {
        setError(
          exception instanceof ApiError
            ? exception.message
            : "The sign-in service could not be reached.",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="grid w-full max-w-4xl gap-5 md:grid-cols-[minmax(0,1fr)_18rem]">
        <Card>
          <CardBody className="p-6 sm:p-8">
            <div className="mb-5 flex items-center gap-3">
              <Image src="/dsn-logo.png" alt="" width={36} height={36} className="rounded-sm" />
              <div>
                <h1 className="text-xl font-semibold text-secondary">Legal Operations Platform</h1>
                <p className="text-sm text-muted-foreground">
                  Data Science Nigeria and EqualyzAI
                </p>
              </div>
            </div>

            <form onSubmit={submit} className="space-y-4">
              <Field label="Work email" required>
                <Input
                  type="email"
                  value={email}
                  autoComplete="username"
                  onChange={(event) => setEmail(event.target.value)}
                />
              </Field>
              <Field label="Password" required>
                <Input
                  type="password"
                  value={password}
                  autoComplete="current-password"
                  onChange={(event) => setPassword(event.target.value)}
                />
              </Field>

              {needsCode ? (
                <Field
                  label="Authenticator code"
                  required
                  hint="Six digits from the authenticator app enrolled on this account."
                >
                  <Input
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={9}
                    value={code}
                    autoFocus
                    onChange={(event) => setCode(event.target.value)}
                  />
                </Field>
              ) : null}

              {error ? (
                <div className="flex items-start gap-1.5 text-sm text-destructive">
                  <span aria-hidden>&#9888;</span>
                  <span>{error}</span>
                </div>
              ) : null}

              <Button type="submit" variant="primary" disabled={busy} className="w-full">
                {busy ? "Signing in" : "Sign in"}
              </Button>
            </form>

            <p className="mt-5 max-w-reading text-sm leading-relaxed text-muted-foreground">
              This is the local sign-in path. Set the deployment to OIDC and the same accounts
              authenticate at Microsoft Entra ID or Google Workspace through Keycloak instead,
              with the roles still coming from this platform. A role that can publish, sign or
              administer needs a second factor either way, and a recovery code works in place of
              the authenticator.
            </p>
          </CardBody>
        </Card>

        <div className="space-y-3">
          <Notice title="Demonstration accounts">
            Every account uses the password{" "}
            <span className="font-mono text-xs">Lop-Demo-2026</span>.
          </Notice>
          <Card>
            <CardBody className="space-y-1 p-2">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  key={account.email}
                  onClick={() => setEmail(account.email)}
                  className="block w-full rounded-md px-3 py-2 text-left text-sm hover:bg-muted"
                >
                  <div className="font-medium capitalize">
                    {account.email.split("@")[0].replaceAll(".", " ")}
                  </div>
                  <div className="text-xs text-muted-foreground">{account.role}</div>
                </button>
              ))}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
