"use client";

import * as React from "react";

import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Field,
  Input,
  KeyValue,
  Modal,
  Mono,
  Notice,
  Pill,
  Refusal,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";

type Status = { enrolled: boolean; required: boolean; recovery_codes_remaining: number };

type Enrolment = { secret: string; provisioning_uri: string; recovery_codes: string[] };

/*
  Enrolment is deliberately two steps. The secret is issued, and the factor
  only goes live once a code proves the authenticator actually holds it.
  Activating on issue would lock someone out whenever the QR code failed to
  scan, which is the failure this is most likely to hit.
*/
export function MfaEnrolment() {
  const status = useApi<Status>("/auth/mfa");
  const [open, setOpen] = React.useState(false);
  const [enrolment, setEnrolment] = React.useState<Enrolment | null>(null);
  const [code, setCode] = React.useState("");

  const start = useAction(async () => {
    const result = await api<Enrolment>("/auth/mfa/enrol", { method: "POST" });
    setEnrolment(result);
    setOpen(true);
  });

  const confirm = useAction(async () => {
    await api("/auth/mfa/confirm", { method: "POST", body: { code } });
    status.reload();
    setOpen(false);
    setEnrolment(null);
    setCode("");
  });

  const data = status.data;

  return (
    <Card>
      <CardHeader
        title="Second factor"
        subtitle="Publishing house position, issuing a signature request, restricting a matter and changing configuration all need one."
        actions={
          data?.enrolled ? (
            <Pill tone="good">Enrolled</Pill>
          ) : (
            <Button variant="primary" disabled={start.busy} onClick={() => void start.run()}>
              Enrol an authenticator
            </Button>
          )
        }
      />
      <CardBody className="space-y-3">
        {start.error ? (
          <Refusal title="Enrolment could not start" reason={start.error.message} />
        ) : null}

        {data?.required && !data.enrolled ? (
          <Notice tone="warn" title="Your role requires a second factor">
            You can sign in and read without one. The privileged actions above will refuse until
            an authenticator is enrolled.
          </Notice>
        ) : null}

        {data ? (
          <KeyValue
            rows={[
              ["Enrolled", data.enrolled ? "Yes" : "No"],
              ["Required for your role", data.required ? "Yes" : "No"],
              ["Recovery codes left", String(data.recovery_codes_remaining)],
            ]}
          />
        ) : null}
      </CardBody>

      <Modal
        open={open}
        title="Enrol an authenticator"
        subtitle="Add the secret to your authenticator app, then enter the code it shows. The factor is not active until that code is accepted."
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={code.trim().length < 6 || confirm.busy}
              onClick={() => void confirm.run()}
            >
              Confirm and activate
            </Button>
          </>
        }
      >
        <Field label="Secret" hint="Enter this in your authenticator if it cannot scan a code.">
          <Mono className="block break-all rounded-md border bg-muted/40 p-3 text-sm">
            {enrolment?.secret}
          </Mono>
        </Field>

        <Notice tone="warn" title="Recovery codes, shown once">
          Each works once, in place of the authenticator, on the day the device is lost. Store
          them somewhere other than the device.
          <div className="mt-2 grid grid-cols-2 gap-1 font-mono text-xs sm:grid-cols-3">
            {(enrolment?.recovery_codes ?? []).map((recovery) => (
              <span key={recovery} className="rounded-sm border bg-card px-2 py-1">
                {recovery}
              </span>
            ))}
          </div>
        </Notice>

        <Field label="Code from the authenticator" required>
          <Input
            inputMode="numeric"
            maxLength={6}
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
        </Field>

        {confirm.error ? (
          <Refusal title="That code was not accepted" reason={confirm.error.message} />
        ) : null}
      </Modal>
    </Card>
  );
}
