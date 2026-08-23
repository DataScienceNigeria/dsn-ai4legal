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

type Enrolment = {
  secret: string;
  provisioning_uri: string;
  provisioning_qr: string;
  recovery_codes: string[];
};

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
  const [showCodes, setShowCodes] = React.useState(false);

  /*
    Reopening this offers the enrolment already under way rather than a new
    one. Rotating the secret on every open invalidated whatever the phone had
    just been given, so the obvious recovery from a failed attempt was the
    thing that guaranteed the next attempt failed too. Start over is the
    deliberate way to get a new secret.
  */
  const start = useAction(async (restart = false) => {
    const result = await api<Enrolment>(
      `/auth/mfa/enrol${restart ? "?restart=true" : ""}`,
      { method: "POST" },
    );
    setEnrolment(result);
    setShowCodes(false);
    setCode("");
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
            <Button variant="primary" disabled={start.busy} onClick={() => void start.run(false)}>
              Enrol an authenticator
            </Button>
          )
        }
      />
      <CardBody className="space-y-3">
        {start.error ? (
          <Refusal title="Enrolment could not start" reason={start.error.message} />
        ) : null}

        {data && !data.required && !data.enrolled ? (
          <Notice tone="info" title="The second factor is not being demanded">
            Either your role does not require one, or the module is switched off for this
            deployment. You can still enrol, and it will be used the moment it is required
            again.
          </Notice>
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
        subtitle="Scan the code with your authenticator app, then enter the number it shows. The factor is not active until that number is accepted."
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              disabled={start.busy}
              onClick={() => void start.run(true)}
              title="Issues a new secret. Delete the old entry from your authenticator first."
            >
              Start over
            </Button>
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
        {/* Typing a base32 secret by hand is where enrolment goes wrong, so
            the code is scanned and the secret is the fallback beneath it. */}
        {enrolment?.provisioning_qr ? (
          <Field label="Scan this with your authenticator" required>
            <div className="flex justify-center rounded-md border bg-white p-4">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={enrolment.provisioning_qr}
                alt="Enrolment code for your authenticator app"
                width={196}
                height={196}
              />
            </div>
          </Field>
        ) : null}

        <Field label="Secret" hint="Enter this in your authenticator if it cannot scan the code.">
          <Mono className="block break-all rounded-md border bg-muted/40 p-3 text-sm">
            {enrolment?.secret}
          </Mono>
        </Field>

        {/* Kept behind a deliberate press. Ten single-use codes on screen is
            the one part of this dialog nobody wants over their shoulder, and
            most people are enrolling a phone they already have in hand. */}
        <Notice tone="warn" title="Recovery codes, shown once">
          Each works once, in place of the authenticator, on the day the device is lost. Store
          them somewhere other than the device. They are not shown again.
          <div className="mt-2">
            <Button size="sm" onClick={() => setShowCodes((previous) => !previous)}>
              {showCodes ? "Hide the recovery codes" : "Show the recovery codes"}
            </Button>
          </div>
          {showCodes ? (
            <div className="mt-2 grid grid-cols-2 gap-1 font-mono text-xs sm:grid-cols-3">
              {(enrolment?.recovery_codes ?? []).map((recovery) => (
                <span key={recovery} className="rounded-sm border bg-card px-2 py-1">
                  {recovery}
                </span>
              ))}
            </div>
          ) : null}
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
          <Refusal
            title="That code was not accepted"
            reason={confirm.error.fieldErrors.code ?? confirm.error.message}
          />
        ) : null}
      </Modal>
    </Card>
  );
}
