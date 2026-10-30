"use client";

import * as React from "react";

import { useSession } from "@/components/app/session";
import { Button, Field, PasswordInput } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { MINIMUM_PASSWORD, newPasswordProblem } from "@/lib/utils";

type Errors = Partial<Record<"current_password" | "new_password" | "confirm", string>>;

const ORDER = ["current_password", "new_password", "confirm"] as const;

/*
  Changing your own password. The same form serves the first sign-in, when an
  administrator's password has to be replaced before anything else, and the
  account page. Each problem is shown under its field and the first one takes
  the focus; what the API refuses comes back the same way, and anything that
  is not about one field sits beside the button.
*/
export function PasswordChangeForm({
  submitLabel = "Change my password",
  onDone,
}: Readonly<{ submitLabel?: string; onDone?: () => void }>) {
  const { me, refresh } = useSession();
  const [current, setCurrent] = React.useState("");
  const [next, setNext] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [errors, setErrors] = React.useState<Errors>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [done, setDone] = React.useState(false);
  const id = React.useId();

  function focusFirst(found: Errors) {
    const first = ORDER.find((name) => found[name]);
    if (first) document.getElementById(`${id}-${first}`)?.focus();
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    setDone(false);

    const found: Errors = {};
    if (!current) found.current_password = "Enter your current password.";
    const problem = newPasswordProblem(next, current, me?.email ?? "");
    if (problem) found.new_password = problem;
    if (!found.new_password && confirm !== next) found.confirm = "This does not match the new password.";
    setErrors(found);
    if (Object.keys(found).length > 0) {
      focusFirst(found);
      return;
    }

    setBusy(true);
    try {
      await api("/auth/password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      setCurrent("");
      setNext("");
      setConfirm("");
      setDone(true);
      await refresh();
      onDone?.();
    } catch (exception) {
      if (exception instanceof ApiError && Object.keys(exception.fieldErrors).length > 0) {
        const returned = exception.fieldErrors as Errors;
        setErrors(returned);
        focusFirst(returned);
      } else {
        setFormError(
          exception instanceof ApiError ? exception.message : "Your password was not changed.",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <Field label="Current password" required error={errors.current_password}>
        <PasswordInput
          id={`${id}-current_password`}
          autoComplete="current-password"
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
          aria-invalid={Boolean(errors.current_password)}
        />
      </Field>
      <Field
        label="New password"
        required
        hint={`At least ${MINIMUM_PASSWORD} characters. Not your email address.`}
        error={errors.new_password}
      >
        <PasswordInput
          id={`${id}-new_password`}
          autoComplete="new-password"
          value={next}
          onChange={(event) => setNext(event.target.value)}
          aria-invalid={Boolean(errors.new_password)}
        />
      </Field>
      <Field label="Confirm the new password" required error={errors.confirm}>
        <PasswordInput
          id={`${id}-confirm`}
          autoComplete="new-password"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          aria-invalid={Boolean(errors.confirm)}
        />
      </Field>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" loading={busy}>
          {submitLabel}
        </Button>
        {formError ? (
          <p role="alert" className="text-sm text-destructive">
            {formError}
          </p>
        ) : null}
        {done ? (
          <p role="status" className="text-sm text-muted-foreground">
            Your password has been changed.
          </p>
        ) : null}
      </div>
    </form>
  );
}
