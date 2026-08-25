"use client";

import * as React from "react";

import { useSession } from "@/components/app/session";
import { Button, Field, Input, Modal, Notice, PasswordInput, Refusal } from "@/components/ui";
import { ApiError, stepUp } from "@/lib/api";

/*
  Publishing a library version, requesting a signature, opening a restricted
  matter and changing configuration all demand a fresh authentication, and for
  the roles that carry a second factor they demand the factor too. The API
  refuses with step_up_required; before this there was nowhere in the interface
  to answer that refusal, so a legal lead could write a draft and never put
  it into force.

  It is one dialog, raised by whichever action was refused and retrying that
  same action once the re-authentication succeeds. Retrying is the point: being
  sent back to find the button again is how people give up.

  The two halves of step-up are separate and the dialog only asks for the half
  that applies. Freshness always applies: the password is asked for whatever
  else is true. The second factor is asked for only when `mfa_required` says
  this person owes one, which is false both when the role carries no factor and
  when the module is switched off entirely. Rendering the code field regardless
  made a disabled module look like a demand nobody could satisfy.
*/
export function StepUpDialog({
  open,
  action,
  onClose,
  onAuthenticated,
}: Readonly<{
  open: boolean;
  action: string;
  onClose: () => void;
  onAuthenticated: () => void;
}>) {
  const { me } = useSession();
  const [password, setPassword] = React.useState("");
  const [code, setCode] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const owesFactor = Boolean(me?.mfa_required);
  const wantsFactor = owesFactor && Boolean(me?.mfa_enrolled);
  const needsEnrolment = owesFactor && !me?.mfa_enrolled;

  React.useEffect(() => {
    if (open) {
      setPassword("");
      setCode("");
      setError(null);
    }
  }, [open]);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await stepUp(me?.email ?? "", password, code);
      onAuthenticated();
      onClose();
    } catch (exception) {
      setError(
        exception instanceof ApiError
          ? exception.message
          : "That re-authentication could not be completed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Confirm it is you"
      subtitle={`${action} needs a fresh authentication. It is asked for again because the act matters, not because anything is wrong with your session.`}
      width="sm"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!password || needsEnrolment || (wantsFactor && code.length < 6) || busy}
            onClick={() => void confirm()}
          >
            {busy ? "Confirming" : "Confirm and continue"}
          </Button>
        </>
      }
    >
      {error ? <Refusal title="That did not confirm" reason={error} /> : null}

      <Field label="Your password" required>
        <PasswordInput
          value={password}
          autoComplete="current-password"
          onChange={(event) => setPassword(event.target.value)}
        />
      </Field>

      {wantsFactor ? (
        <Field
          label="Authenticator code"
          required
          hint="Your role carries a second factor, so this act needs it as well as the password."
        >
          <Input
            value={code}
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="123456"
            onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
          />
        </Field>
      ) : null}

      {needsEnrolment ? (
        <Notice tone="warn" title="No authenticator yet">
          Your role requires a second factor and none is enrolled, so this act cannot complete.
          Enrol one under Administration, in the Security tab.
        </Notice>
      ) : null}
    </Modal>
  );
}

/*
  One line at each privileged call site. Every such action already runs through
  useAction, which now recognises the refusal and holds the arguments, so all a
  screen has to do is say what was being attempted.
*/
export function StepUpGate({
  action,
  state,
}: Readonly<{
  action: string;
  state: {
    stepUpFor: string | null;
    dismissStepUp: () => void;
    retry: () => Promise<void>;
  };
}>) {
  return (
    <StepUpDialog
      open={state.stepUpFor !== null}
      action={action}
      onClose={state.dismissStepUp}
      onAuthenticated={() => void state.retry()}
    />
  );
}

