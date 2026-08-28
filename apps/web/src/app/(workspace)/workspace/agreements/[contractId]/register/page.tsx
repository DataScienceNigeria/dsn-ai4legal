"use client";

import { useParams } from "next/navigation";
import * as React from "react";

import { AgreementHeader } from "@/components/app/agreement-header";
import { useRoles } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Field,
  Input,
  Notice,
  Refusal,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Contract, UserRow, Vocabulary } from "@/lib/types";
import { formatDate } from "@/lib/utils";

/*
  The register entry, section 14 of the guide.

  These columns existed and had nowhere to be edited, which is the same as not
  existing. The two that matter are the owner and the department: an agreement
  with no named owner and no recorded department is one nobody can be asked
  about, and that is the whole reason the register lived in a spreadsheet.

  Ending an agreement is not here. It goes through closure, which checks that
  the data came back.
*/
export default function RegisterEntry() {
  const { contractId } = useParams<{ contractId: string }>();
  const { has } = useRoles();
  const canEdit = has("counsel", "head_of_legal", "admin");

  const contract = useApi<Contract>(`/contracts/${contractId}`, [contractId]);
  const users = useApi<UserRow[]>("/users");
  const vocabulary = useApi<Vocabulary>("/lifecycle/vocabulary");

  const [form, setForm] = React.useState<Record<string, string>>({});
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    const record = contract.data;
    if (!record) return;
    setForm({
      user_department: record.user_department ?? "",
      contract_owner_id: record.contract_owner_name ? "" : "",
      payment_terms: record.payment_terms ?? "",
      key_deliverables: record.key_deliverables ?? "",
      termination_deadline: record.termination_deadline ?? "",
      remarks: record.remarks ?? "",
      status: record.status,
    });
  }, [contract.data]);

  const save = useAction(async () => {
    await api(`/contracts/${contractId}/register`, {
      method: "PATCH",
      body: {
        user_department: form.user_department || null,
        contract_owner_id: form.contract_owner_id || null,
        payment_terms: form.payment_terms || null,
        key_deliverables: form.key_deliverables || null,
        termination_deadline: form.termination_deadline || null,
        remarks: form.remarks || null,
        status: form.status || null,
      },
    });
    setSaved(true);
    contract.reload();
  });

  function set(name: string, value: string) {
    setSaved(false);
    setForm((previous) => ({ ...previous, [name]: value }));
  }

  if (contract.loading) return <Spinner />;
  if (contract.error || !contract.data) {
    return <Refusal title="That agreement is not available to you" reason={contract.error?.message} />;
  }

  const record = contract.data;
  const live = ["executed", "active", "in_closure"];

  return (
    <div className="space-y-5">
      <AgreementHeader
        contractId={contractId}
        title="Register entry"
        subtitle="How the organisation finds and runs this agreement, as against what the parties agreed."
      />

      {saved ? (
        <Notice tone="good" title="Recorded">
          The register entry for {record.reference} was updated.
        </Notice>
      ) : null}
      {save.error ? (
        <Refusal
          title="That was not recorded"
          reason={save.error.message}
          reasons={save.error.reasons}
        />
      ) : null}

      <Card>
        <CardHeader
          title="Who owns it"
          subtitle="An agreement with no named owner and no recorded department is one nobody can be asked about."
        />
        <CardBody className="grid gap-4 sm:grid-cols-2">
          <Field label="User department" hint="The team that runs it day to day.">
            <Input
              value={form.user_department ?? ""}
              readOnly={!canEdit}
              onChange={(event) => set("user_department", event.target.value)}
              placeholder="Engineering"
            />
          </Field>
          <Field
            label="Contract owner"
            hint={
              record.contract_owner_name
                ? `Currently ${record.contract_owner_name}.`
                : "Nobody is named yet."
            }
          >
            <Select
              value={form.contract_owner_id ?? ""}
              disabled={!canEdit}
              onChange={(event) => set("contract_owner_id", event.target.value)}
            >
              <option value="">Leave as it is</option>
              {(users.data ?? [])
                .filter((person) => person.active)
                .map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
            </Select>
          </Field>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="What it requires" />
        <CardBody className="space-y-4">
          <Field label="Key deliverables">
            <Textarea
              value={form.key_deliverables ?? ""}
              readOnly={!canEdit}
              onChange={(event) => set("key_deliverables", event.target.value)}
              className="min-h-[5rem] leading-relaxed"
            />
          </Field>
          <Field label="Payment terms">
            <Textarea
              value={form.payment_terms ?? ""}
              readOnly={!canEdit}
              onChange={(event) => set("payment_terms", event.target.value)}
              className="min-h-[4rem] leading-relaxed"
            />
          </Field>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Dates and status" />
        <CardBody className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Termination deadline"
            hint="The last day notice can be given. Derived from the end date and the notice period, and overridable, because a contract naming a date in words beats the arithmetic."
          >
            <Input
              type="date"
              value={form.termination_deadline ?? ""}
              readOnly={!canEdit}
              onChange={(event) => set("termination_deadline", event.target.value)}
            />
          </Field>
          <Field
            label="Status"
            hint="Ending an agreement goes through closure, which checks that the data came back."
          >
            <Select
              value={form.status ?? ""}
              disabled={!canEdit}
              onChange={(event) => set("status", event.target.value)}
            >
              {(vocabulary.data?.contract_statuses ?? [])
                .filter((term) => live.includes(term.key))
                .map((term) => (
                  <option key={term.key} value={term.key}>
                    {term.label}
                  </option>
                ))}
            </Select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="Remarks">
              <Textarea
                value={form.remarks ?? ""}
                readOnly={!canEdit}
                onChange={(event) => set("remarks", event.target.value)}
                className="min-h-[4rem] leading-relaxed"
              />
            </Field>
          </div>
        </CardBody>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        {canEdit ? (
          <Button variant="primary" disabled={save.busy} onClick={() => void save.run()}>
            Record it
          </Button>
        ) : (
          <span className="text-sm text-muted-foreground">Legal keeps the register.</span>
        )}
        {record.effective_date ? (
          <span className="text-xs text-muted-foreground">
            {`Effective ${formatDate(record.effective_date)}`}
          </span>
        ) : null}
      </div>
    </div>
  );
}
