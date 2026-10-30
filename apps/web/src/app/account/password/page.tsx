"use client";

import { useRouter } from "next/navigation";

import { PasswordChangeForm } from "@/components/app/password-change";
import { useSession } from "@/components/app/session";
import { Card, CardBody, CardHeader, PageTitle, Spinner } from "@/components/ui";
import { homeFor } from "@/lib/api";

/*
  Where an account holding an administrator's password is held until it has
  chosen its own. The API refuses everything else in the meantime, so nothing
  on this page needs more than the session and the change itself.
*/
export default function ChoosePasswordPage() {
  const router = useRouter();
  const { me, loading } = useSession();

  if (loading || !me) return <Spinner label="Opening your account" />;

  const required = me.password_must_change;

  return (
    <div className="space-y-6">
      <PageTitle
        title={required ? "Choose your own password" : "Change your password"}
        subtitle={
          required
            ? "Your password was set by an administrator, so somebody else knows it. Choose one only you know before you continue."
            : "Change the password you sign in with."
        }
      />
      <Card>
        <CardHeader title={me.email} subtitle="Enter the password you signed in with, then the new one twice." />
        <CardBody>
          <PasswordChangeForm
            submitLabel={required ? "Save and continue" : "Change my password"}
            onDone={() => router.replace(homeFor(me.roles))}
          />
        </CardBody>
      </Card>
    </div>
  );
}
