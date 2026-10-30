"use client";

import { MfaEnrolment } from "@/components/app/mfa-enrolment";
import { PasswordChangeForm } from "@/components/app/password-change";
import { useSession } from "@/components/app/session";
import { Card, CardBody, CardHeader, KeyValue, PageTitle, Spinner } from "@/components/ui";
import { ENTITY_NAMES, ROLE_LABELS, titleCase } from "@/lib/utils";

/*
  Everything about an account its holder looks after: who the platform takes
  them to be, the password and the second factor. Name, roles and
  organisations are shown but not edited here, because they decide what the
  person may reach and an administrator changes them, on the audit.
*/
export default function AccountPage() {
  const { me, loading } = useSession();

  if (loading || !me) return <Spinner label="Opening your account" />;

  return (
    <div className="space-y-6">
      <PageTitle title="Account settings" subtitle="Your profile, your password and your second factor." />

      <Card>
        <CardHeader
          title="Profile"
          subtitle="Set by an administrator. Ask one if any of this is wrong."
        />
        <CardBody>
          <KeyValue
            rows={[
              ["Name", me.name],
              ["Email", me.email],
              ["Roles", me.roles.map((role) => ROLE_LABELS[role] ?? titleCase(role)).join(", ")],
              ["Organisations", me.entities.map((code) => ENTITY_NAMES[code] ?? code).join(", ")],
            ]}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Password"
          subtitle="Enter your current password, then the new one twice."
        />
        <CardBody>
          <PasswordChangeForm />
        </CardBody>
      </Card>

      <MfaEnrolment />
    </div>
  );
}
