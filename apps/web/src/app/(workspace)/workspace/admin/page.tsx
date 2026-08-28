"use client";

import * as React from "react";

import { Icon } from "@/components/app/icons";
import { MfaEnrolment } from "@/components/app/mfa-enrolment";
import { useRoles, useSession } from "@/components/app/session";
import { StepUpGate } from "@/components/app/step-up";
import {
  Actions,
  Button,
  Card,
  CardBody,
  CardHeader,
  Confirm,
  DataState,
  Field,
  Input,
  Modal,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Row,
  Select,
  Tabs,
  Textarea,
} from "@/components/ui";
import { api, download, query } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type {
  AuditRow,
  ConnectorRow,
  DeletionRow,
  ExportRow,
  OrganisationRow,
  QualitySampleRow,
  RetentionRow,
  UserRow,
} from "@/lib/types";
import { cn, decisionTone, entityTone, formatDateTime, titleCase } from "@/lib/utils";

const RETENTION_COLS = "minmax(0,1fr) 6.875rem 8.75rem 8.125rem minmax(0,1.2fr)";
const EXPORT_COLS = "9.375rem minmax(0,1.4fr) 7.5rem 10rem";
const DELETION_COLS = "8.75rem minmax(0,1.2fr) 7.5rem 11.25rem 10rem";
const CONNECTOR_COLS = "minmax(0,1.2fr) 6.875rem minmax(0,1.4fr) 11.875rem 6.25rem";
const PEOPLE_COLS = "minmax(0,1.2fr) minmax(0,1.1fr) 6.25rem 8.75rem 6.875rem 8.75rem";
const CONFIG_COLS = "minmax(0,1fr) minmax(0,1.6fr) 5rem 7.5rem";
const SAMPLE_COLS = "7.5rem 9.375rem minmax(0,1fr) 8.125rem 9.375rem";

const CONFIG_AREAS = [
  "sla",
  "tiering",
  "authority",
  "retention",
  "notifications",
  "ai",
  "intake",
];

const SAMPLE_OUTCOMES = ["sound", "minor_issue", "material_issue"];
const AUDIT_COLS = "10.625rem 10rem minmax(0,1fr) 9.375rem 5.625rem";

const RECORD_CLASSES = [
  "matter",
  "contract",
  "document",
  "communication",
  "assessment",
  "audit_event",
];

function SecondApproval({
  status,
  decidedAt,
  busy,
  onDecide,
}: Readonly<{
  status: string;
  decidedAt: string | null;
  busy: boolean;
  onDecide: (approve: boolean) => void;
}>) {
  if (status !== "pending") {
    return (
      <span className="text-xs text-muted-foreground">
        {decidedAt === null ? "Not decided" : formatDateTime(decidedAt)}
      </span>
    );
  }
  return (
    <div className="flex gap-2">
      <Button size="sm" variant="primary" disabled={busy} onClick={() => onDecide(true)}>
        Approve
      </Button>
      <Button size="sm" disabled={busy} onClick={() => onDecide(false)}>
        Refuse
      </Button>
    </div>
  );
}

function CertificateCell({ reference }: Readonly<{ reference: string | null }>) {
  if (reference === null) {
    return <span className="text-xs text-muted-foreground">Not issued</span>;
  }
  return <Mono>{reference}</Mono>;
}

function Retention() {
  const policies = useApi<RetentionRow[]>("/retention");
  const [reason, setReason] = React.useState<Record<string, string>>({});
  const rows = policies.data ?? [];

  const toggle = useAction(async (recordClass: string, hold: boolean) => {
    await api(`/retention/${recordClass}/hold`, {
      method: "POST",
      body: { hold, reason: hold ? reason[recordClass] : null },
    });
    policies.reload();
  });

  return (
    <div className="space-y-4">
      <Notice tone="info" title="A hold outranks every role">
        While a record class is under legal hold no role can delete anything in it, including the
        platform administrator. Lifting a hold is an audited act.
      </Notice>

      {toggle.error ? (
        <Refusal title="That hold was not changed" reason={toggle.error.message} />
      ) : null}

      <StepUpGate action="Placing or lifting a legal hold" state={toggle} />

      <Card>
        <CardHeader title="Retention schedules" />
        <div className="table-scroll">
          <div className="min-w-[55rem]">
            <Row cols={RETENTION_COLS} head>
              <div>Record class</div>
              <div>Retain</div>
              <div>Second approval</div>
              <div>Legal hold</div>
              <div>Hold</div>
            </Row>
            <DataState
              loading={policies.loading}
              errorMessage={policies.error?.message}
              errorTitle="Retention is not available to you"
              isEmpty={rows.length === 0}
              emptyTitle="No retention policy is configured"
            >
              {rows.map((policy) => (
                <Row key={policy.record_class} cols={RETENTION_COLS}>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">
                      {titleCase(policy.record_class)}
                    </div>
                    {policy.description ? (
                      <div className="truncate text-xs text-muted-foreground">
                        {policy.description}
                      </div>
                    ) : null}
                  </div>
                  <div className="text-sm">{`${policy.retain_years} years`}</div>
                  <div className="text-sm">
                    {policy.deletion_requires_approval ? "Required" : "Not required"}
                  </div>
                  <div>
                    <Pill tone={policy.legal_hold ? "bad" : "neutral"}>
                      {policy.legal_hold ? "Under hold" : "No hold"}
                    </Pill>
                  </div>
                  <div>
                    {policy.legal_hold ? (
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground">{policy.hold_reason}</p>
                        <Button
                          size="sm"
                          disabled={toggle.busy}
                          onClick={() => toggle.run(policy.record_class, false)}
                        >
                          Lift the hold
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-end gap-2">
                        <Field label="Reason">
                          <Input
                            value={reason[policy.record_class] ?? ""}
                            onChange={(event) =>
                              setReason({
                                ...reason,
                                [policy.record_class]: event.target.value,
                              })
                            }
                            placeholder="Why the hold is needed"
                          />
                        </Field>
                        <Button
                          size="sm"
                          variant="destructive"
                          disabled={toggle.busy || (reason[policy.record_class] ?? "") === ""}
                          onClick={() => toggle.run(policy.record_class, true)}
                        >
                          Place a hold
                        </Button>
                      </div>
                    )}
                  </div>
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>
    </div>
  );
}

function Boundary() {
  const exports = useApi<ExportRow[]>("/exports");
  const deletions = useApi<DeletionRow[]>("/deletions");
  const [form, setForm] = React.useState({ record_class: RECORD_CLASSES[0], reason: "" });
  const [certificates, setCertificates] = React.useState<Record<string, string>>({});

  const requestExport = useAction(async () => {
    await api("/exports", {
      method: "POST",
      body: { record_class: form.record_class, reason: form.reason, data_classes: ["internal"] },
    });
    setForm({ ...form, reason: "" });
    exports.reload();
  });

  const decideExport = useAction(async (id: string, approve: boolean) => {
    await api(`/exports/${id}/decision`, { method: "POST", body: { approve } });
    exports.reload();
  });

  const decideDeletion = useAction(async (id: string, approve: boolean) => {
    await api(`/deletions/${id}/decision`, { method: "POST", body: { approve } });
    deletions.reload();
  });

  const issueCertificate = useAction(async (id: string) => {
    const result = await api<{ certificate_reference: string }>(
      `/deletions/${id}/certificate`,
      { method: "POST" },
    );
    setCertificates((previous) => ({ ...previous, [id]: result.certificate_reference }));
    deletions.reload();
  });

  const error =
    requestExport.error ?? decideExport.error ?? decideDeletion.error ?? issueCertificate.error;
  const exportRows = exports.data ?? [];
  const deletionRows = deletions.data ?? [];

  return (
    <div className="space-y-4">
      <Notice tone="warn" title="Nobody approves their own export or deletion">
        Bulk export and deletion both need a second authorised user, and the platform refuses the
        person who raised the request. Restricted content is never exportable in bulk.
      </Notice>

      {error ? <Refusal title="That action was refused" reason={error.message} /> : null}

      <StepUpGate action="Approving a bulk export" state={decideExport} />
      <StepUpGate action="Approving a deletion" state={decideDeletion} />

      <Card>
        <CardHeader title="Request a bulk export" />
        <CardBody>
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Record class">
              <Select
                value={form.record_class}
                onChange={(event) => setForm({ ...form, record_class: event.target.value })}
              >
                {RECORD_CLASSES.map((value) => (
                  <option key={value} value={value}>
                    {titleCase(value)}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="min-w-[17.5rem] flex-1">
              <Field label="Reason">
                <Textarea
                  rows={2}
                  value={form.reason}
                  onChange={(event) => setForm({ ...form, reason: event.target.value })}
                  placeholder="What the export is for and who asked for it"
                />
              </Field>
            </div>
            <Button
              variant="primary"
              disabled={requestExport.busy || form.reason === ""}
              onClick={() => requestExport.run()}
            >
              Request
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Export requests" />
        <div className="table-scroll">
          <div className="min-w-[51.25rem]">
            <Row cols={EXPORT_COLS} head>
              <div>Record class</div>
              <div>Reason</div>
              <div>Status</div>
              <div>Second approval</div>
            </Row>
            <DataState
              loading={exports.loading}
              errorMessage={exports.error?.message}
              errorTitle="Exports are not available to you"
              isEmpty={exportRows.length === 0}
              emptyTitle="No export has been requested"
            >
              {exportRows.map((row) => (
                <Row key={row.id} cols={EXPORT_COLS}>
                  <div className="text-sm">{titleCase(row.record_class)}</div>
                  <div className="text-sm">{row.reason}</div>
                  <div>
                    <Pill tone={decisionTone(row.status)}>{titleCase(row.status)}</Pill>
                  </div>
                  <div>
                    <SecondApproval
                      status={row.status}
                      decidedAt={row.decided_at}
                      busy={decideExport.busy}
                      onDecide={(approve) => decideExport.run(row.id, approve)}
                    />
                  </div>
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Deletion requests"
          subtitle="An approved deletion produces a certificate, and the certificate is retained."
        />
        <div className="table-scroll">
          <div className="min-w-[56.25rem]">
            <Row cols={DELETION_COLS} head>
              <div>Record class</div>
              <div>Object</div>
              <div>Status</div>
              <div>Certificate</div>
              <div>Action</div>
            </Row>
            <DataState
              loading={deletions.loading}
              errorMessage={deletions.error?.message}
              errorTitle="Deletions are not available to you"
              isEmpty={deletionRows.length === 0}
              emptyTitle="No deletion has been requested"
            >
              {deletionRows.map((row) => (
                <Row key={row.id} cols={DELETION_COLS}>
                  <div className="text-sm">{titleCase(row.record_class)}</div>
                  <div className="min-w-0">
                    <div className="truncate text-sm">{row.object_reference}</div>
                    <div className="truncate text-xs text-muted-foreground">{row.reason}</div>
                  </div>
                  <div>
                    <Pill tone={decisionTone(row.status)}>{titleCase(row.status)}</Pill>
                  </div>
                  <div>
                    <CertificateCell
                      reference={row.certificate_reference ?? certificates[row.id] ?? null}
                    />
                  </div>
                  <div className="flex gap-2">
                    {row.status === "pending" ? (
                      <>
                        <Button
                          size="sm"
                          variant="primary"
                          disabled={decideDeletion.busy}
                          onClick={() => decideDeletion.run(row.id, true)}
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          disabled={decideDeletion.busy}
                          onClick={() => decideDeletion.run(row.id, false)}
                        >
                          Refuse
                        </Button>
                      </>
                    ) : null}
                    {row.status === "approved" && row.certificate_reference === null ? (
                      <Button
                        size="sm"
                        disabled={issueCertificate.busy}
                        onClick={() => issueCertificate.run(row.id)}
                      >
                        Issue certificate
                      </Button>
                    ) : null}
                  </div>
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>
    </div>
  );
}

function Connectors() {
  const connectors = useApi<ConnectorRow[]>("/connectors");
  const rows = connectors.data ?? [];
  return (
    <Card>
      <CardHeader
        title="Every route out of the platform"
        subtitle="A connector that is not registered here cannot carry data anywhere."
      />
      <div className="table-scroll">
        <div className="min-w-[56.25rem]">
          <Row cols={CONNECTOR_COLS} head>
            <div>Connector</div>
            <div>Direction</div>
            <div>Purpose</div>
            <div>Permitted classes</div>
            <div>Active</div>
          </Row>
          <DataState
            loading={connectors.loading}
            errorMessage={connectors.error?.message}
            errorTitle="Connectors are not available to you"
            isEmpty={rows.length === 0}
            emptyTitle="No connector is registered"
          >
            {rows.map((row) => (
              <Row key={row.code} cols={CONNECTOR_COLS}>
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{row.name}</div>
                  <Mono>{row.code}</Mono>
                </div>
                <div className="text-sm">{titleCase(row.direction)}</div>
                <div className="text-sm">{row.purpose}</div>
                <div className="flex flex-wrap gap-1">
                  {row.permitted_data_classes.map((value) => (
                    <Pill key={value} tone={value === "restricted" ? "bad" : "neutral"}>
                      {titleCase(value)}
                    </Pill>
                  ))}
                </div>
                <div>
                  <Pill tone={row.active ? "good" : "neutral"}>
                    {row.active ? "Active" : "Off"}
                  </Pill>
                </div>
              </Row>
            ))}
          </DataState>
        </div>
      </div>
    </Card>
  );
}

/*
  Clearing someone else's second factor is the request an attacker would most
  like to make, so it is bounded rather than convenient: administrators only,
  a fresh authentication, a reason that is recorded against both accounts, and
  it enrols nothing in its place. The next privileged act that person attempts
  refuses until they have enrolled a new device.
*/
function ResetSecondFactor({
  user,
  onDone,
}: Readonly<{ user: UserRow; onDone: () => void }>) {
  const { has } = useRoles();
  const { me } = useSession();
  const [open, setOpen] = React.useState(false);

  const reset = useAction(async (reason: string) => {
    await api(`/users/${user.id}/mfa/reset`, { method: "POST", body: { reason } });
    onDone();
    setOpen(false);
  });

  if (!has("admin") || user.id === me?.id) return null;

  return (
    <>
      <Button size="sm" variant="destructive" onClick={() => setOpen(true)}>
        Reset
      </Button>
      <Confirm
        open={open}
        title={`Reset the second factor for ${user.name}`}
        detail="Their authenticator and every recovery code stop working. They enrol a new device themselves, and until they do, anything needing a step-up refuses."
        confirmLabel="Reset it"
        destructive
        reasonLabel="Why"
        busy={reset.busy}
        error={reset.error?.message}
        onCancel={() => setOpen(false)}
        onConfirm={(reason: string) => void reset.run(reason)}
      />
      <StepUpGate action="Resetting someone else's second factor" state={reset} />
    </>
  );
}

function People() {
  const users = useApi<UserRow[]>("/users");
  const rows = users.data ?? [];
  return (
    <Card>
      <CardHeader
        title="People and effective permission"
        subtitle="Permission is the intersection of role, entity and matter access."
      />
      <div className="table-scroll">
        <div className="min-w-[53.75rem]">
          <Row cols={PEOPLE_COLS} head>
            <div>Name</div>
            <div>Roles</div>
            <div>Entities</div>
            <div>Specialisms</div>
            <div>Workload</div>
            <div>Second factor</div>
          </Row>
          <DataState
            loading={users.loading}
            errorMessage={users.error?.message}
            errorTitle="People are not available to you"
            isEmpty={rows.length === 0}
            emptyTitle="No person is registered"
          >
            {rows.map((user) => (
              <Row key={user.id} cols={PEOPLE_COLS}>
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{user.name}</div>
                  <div className="truncate text-xs text-muted-foreground">{user.work_email}</div>
                </div>
                <div className="flex flex-wrap gap-1">
                  {user.roles.map((role) => (
                    <Pill key={role} tone="neutral">
                      {titleCase(role)}
                    </Pill>
                  ))}
                </div>
                <div className="text-sm">{user.entities.join(", ")}</div>
                <div className="text-xs text-muted-foreground">
                  {user.specialisms.length > 0 ? user.specialisms.join(", ") : "None recorded"}
                </div>
                <div className="text-sm">
                  <Pill tone={user.workload >= user.workload_ceiling ? "warn" : "neutral"}>
                    {`${user.workload} of ${user.workload_ceiling}`}
                  </Pill>
                </div>
                <div>
                  <ResetSecondFactor user={user} onDone={() => users.reload()} />
                </div>
              </Row>
            ))}
          </DataState>
        </div>
      </div>
    </Card>
  );
}

function Audit() {
  const [action, setAction] = React.useState("");
  const query = action === "" ? "" : `?action=${encodeURIComponent(action)}`;
  const events = useApi<AuditRow[]>(`/audit/events${query}`, [action]);
  const verify = useApi<{ reconciled: boolean; message: string }>("/audit/verify");
  const rows = events.data ?? [];

  /*
    The export carries the same filter as the screen, so what you take away is
    what you were looking at. It also carries the chain columns the table has
    no room for, which is what makes the file checkable rather than a list of
    assertions. Exporting is itself an audited act.
  */
  const save = useAction(async () => {
    const stamp = new Date().toISOString().slice(0, 10);
    await download(`/audit/events.csv${query}`, `audit-${stamp}.csv`);
  });

  return (
    <div className="space-y-4">
      {verify.data ? (
        <Notice tone={verify.data.reconciled ? "good" : "warn"} title="Audit chain">
          {verify.data.message}
        </Notice>
      ) : null}

      <Card>
        <CardHeader
          title="Audit trail"
          subtitle="Append-only for the retention period. Administrators cannot alter it."
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <Input
                value={action}
                onChange={(event) => setAction(event.target.value)}
                placeholder="Filter by action"
              />
              <Button size="sm" disabled={save.busy} onClick={() => void save.run()}>
                <Icon name="archive" className="h-4 w-4" />
                {save.busy ? "Preparing" : "Export CSV"}
              </Button>
            </div>
          }
        />
        {save.error ? (
          <CardBody className="border-b">
            <Refusal title="The export was refused" reason={save.error.message} />
          </CardBody>
        ) : null}
        <div className="table-scroll">
          <div className="min-w-[56.25rem]">
            <Row cols={AUDIT_COLS} head>
              <div>When</div>
              <div>Actor</div>
              <div>Action</div>
              <div>Object</div>
              <div>Result</div>
            </Row>
            <DataState
              loading={events.loading}
              errorMessage={events.error?.message}
              errorTitle="The audit trail is not available to you"
              isEmpty={rows.length === 0}
              emptyTitle="No event matches"
            >
              {rows.map((event) => (
                <Row key={event.id} cols={AUDIT_COLS}>
                  <div className="text-xs text-muted-foreground">
                    {formatDateTime(event.occurred_at)}
                  </div>
                  <div className="truncate text-sm">{event.actor_label}</div>
                  <div className="min-w-0">
                    <div className="truncate text-sm">{event.action.replaceAll("_", " ")}</div>
                    {event.detail ? (
                      <div className="truncate text-xs text-muted-foreground">{event.detail}</div>
                    ) : null}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-xs">{event.object_type}</div>
                    {event.object_id ? <Mono>{event.object_id}</Mono> : null}
                  </div>
                  <div>
                    <Pill tone={event.result === "success" ? "neutral" : "bad"}>
                      {titleCase(event.result)}
                    </Pill>
                  </div>
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>
    </div>
  );
}

/*
  Configuration without deployment. Every change is a new version rather than
  an edit, so the value that applied on any past date is still recoverable, and
  a change needs a fresh authentication.
*/
type ConfigRow = {
  area: string;
  key: string;
  value: unknown;
  version: number;
  description?: string | null;
};

/*
  What an agreement names us by, held once per entity instead of typed into
  each document. Two people typing a registered address from memory is two
  versions of it in the archive, and the one that reaches an executed contract
  is whichever was typed last.
*/
const ORGANISATION_FIELDS: { name: keyof OrganisationRow; label: string; hint?: string }[] = [
  { name: "legal_name", label: "Legal name", hint: "Exactly as registered. This is what every agreement calls this entity." },
  { name: "trading_name", label: "Trading name", hint: "Only where it differs from the legal name." },
  { name: "registration_number", label: "Registration number" },
  { name: "tax_identification_number", label: "Tax identification number" },
  { name: "registered_address", label: "Registered address", hint: "One line, as it should read in a preamble." },
  { name: "default_jurisdiction", label: "Governing law", hint: "Used where a template leaves the jurisdiction blank." },
  { name: "contact_email", label: "Contact email" },
  { name: "contact_phone", label: "Contact phone" },
  { name: "website", label: "Website" },
  { name: "signatory_name", label: "Default signatory" },
  { name: "signatory_title", label: "Signatory title" },
];

function OrganisationCard({
  record,
  onSaved,
}: Readonly<{ record: OrganisationRow; onSaved: () => void }>) {
  const [draft, setDraft] = React.useState<Record<string, string>>({});

  const save = useAction(async () => {
    await api(`/organisations/${record.entity_code}`, { method: "PATCH", body: draft });
    setDraft({});
    onSaved();
  });

  const value = (name: keyof OrganisationRow) =>
    draft[name] ?? (record[name] as string | null) ?? "";

  const changed = Object.keys(draft).length > 0;
  const tone = entityTone(record.entity_code);
  const renaming =
    typeof draft.legal_name === "string" &&
    draft.legal_name.trim() !== "" &&
    draft.legal_name.trim() !== record.legal_name;

  return (
    /*
      Titled by the entity code in the organisation's own fixed hue, blue for
      DSN and green for EqualyzAI, rather than in --brand. --brand is whichever
      organisation you are currently in, so it would paint whatever is on
      screen the same colour and say nothing about which record this is.
    */
    <Card className={tone.edge}>
      <CardHeader
        title={
          <span className="flex flex-wrap items-center gap-2.5">
            <span className={cn("rounded-md px-2 py-0.5 font-mono text-sm", tone.chip)}>
              {record.entity_code}
            </span>
            <span>{record.legal_name}</span>
          </span>
        }
        subtitle={`Every agreement ${record.entity_code} signs names this entity by these particulars.`}
        actions={
          record.incomplete.length ? (
            <Pill tone="warn">{record.incomplete.length} still to fill</Pill>
          ) : (
            <Pill tone="good">Complete</Pill>
          )
        }
      />
      <CardBody className="space-y-4">
        {renaming ? (
          <Notice tone="bad" title={`This renames ${record.entity_code}`}>
            {`${record.legal_name} becomes ${draft.legal_name}. The legal name is what every
            future agreement calls ${record.entity_code}, and it is a different organisation
            from the other card on this page. Check you are editing the one you meant.`}
          </Notice>
        ) : null}
        {record.incomplete.length ? (
          <Notice tone="warn" title="Generation will ask for these on every document">
            {record.incomplete.join(", ")}. A template that names one of them refuses until the
            record answers it, so filling them here is one edit rather than a question every time.
          </Notice>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          {ORGANISATION_FIELDS.map((field) => (
            <Field key={field.name} label={field.label} hint={field.hint}>
              <Input
                value={value(field.name)}
                onChange={(event) =>
                  setDraft((previous) => ({ ...previous, [field.name]: event.target.value }))
                }
              />
            </Field>
          ))}
        </div>

        <StepUpGate action="Changing an organisation's particulars" state={save} />
        {save.error ? (
          <Refusal
            title="That change was refused"
            reason={save.error.message}
            reasons={Object.values(save.error.fieldErrors ?? {})}
          />
        ) : null}

        <Actions>
          <Button variant="primary" disabled={!changed || save.busy} onClick={() => void save.run()}>
            {save.busy ? "Saving" : "Save these particulars"}
          </Button>
          {changed ? <Button onClick={() => setDraft({})}>Discard changes</Button> : null}
          <span className="text-xs text-muted-foreground sm:ml-auto">
            These values are copied verbatim into executed contracts, so the change is audited
            with both states.
          </span>
        </Actions>
      </CardBody>
    </Card>
  );
}

/*
  One organisation, the one you are working in. Both were shown side by side,
  which is the only screen in the workspace that did, and two near-identical
  names in two identical cards is how the wrong record came to be renamed. The
  entity switch reaches the other, exactly as it does everywhere else.
*/
function Organisations() {
  const { entity } = useSession();
  const record = useApi<OrganisationRow>("/organisations", [entity]);
  const other = entity === "DSN" ? "EqualyzAI" : "Data Science Nigeria";

  return (
    <div className="space-y-4">
      <DataState
        loading={record.loading}
        errorMessage={record.error?.message}
        isEmpty={!record.data}
        emptyTitle="No organisation is configured for this entity"
      >
        {record.data ? (
          <OrganisationCard record={record.data} onSaved={record.reload} />
        ) : null}
      </DataState>
      <p className="text-xs text-muted-foreground">
        {`These are ${entity}'s particulars only. Switch organisation in the sidebar to read or
        change ${other}'s.`}
      </p>
    </div>
  );
}

function Configuration() {
  const [area, setArea] = React.useState("sla");
  const settings = useApi<ConfigRow[]>(`/config/${area}`, [area]);
  const [editing, setEditing] = React.useState<ConfigRow | null>(null);
  const [draft, setDraft] = React.useState("");
  const [newKey, setNewKey] = React.useState("");

  const save = useAction(async (key: string, raw: string, version: number) => {
    let parsed: unknown = raw;
    try {
      parsed = JSON.parse(raw);
    } catch {
      // Not JSON, so the value is stored as the plain string that was typed.
    }
    await api(`/config/${area}`, {
      method: "PATCH",
      body: { area, key, value: parsed, version, description: editing?.description ?? null },
    });
    settings.reload();
    setEditing(null);
    setNewKey("");
  });

  const rows = settings.data ?? [];

  return (
    <div className="space-y-4">
      <Notice tone="info" title="Configuration is versioned, not overwritten">
        Changing a value creates a new version and retires the old one. The change needs a fresh
        authentication and lands on the audit trail with both the before and the after.
      </Notice>

      {save.error ? (
        <Refusal title="That change was refused" reason={save.error.message} />
      ) : null}

      <StepUpGate action="Changing platform configuration" state={save} />

      <Card>
        <CardHeader
          title="Settings"
          actions={
            <>
              <Select value={area} onChange={(event) => setArea(event.target.value)}>
                {CONFIG_AREAS.map((value) => (
                  <option key={value} value={value}>
                    {titleCase(value)}
                  </option>
                ))}
              </Select>
              <Input
                className="w-44"
                placeholder="New key"
                value={newKey}
                onChange={(event) => setNewKey(event.target.value)}
              />
              <Button
                disabled={!newKey.trim()}
                onClick={() =>
                  setEditing({ area, key: newKey.trim(), value: "", version: 0 })
                }
              >
                Add a setting
              </Button>
            </>
          }
        />
        <div className="table-scroll">
          <div className="min-w-[50rem]">
            <Row cols={CONFIG_COLS} head>
              <div>Key</div>
              <div>Value</div>
              <div>Version</div>
              <div>Action</div>
            </Row>
            <DataState
              loading={settings.loading}
              errorMessage={settings.error?.message}
              isEmpty={rows.length === 0}
              emptyTitle="Nothing is configured in this area"
            >
              {rows.map((row) => (
                <Row key={`${row.area}.${row.key}`} cols={CONFIG_COLS}>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{row.key}</div>
                    {row.description ? (
                      <div className="truncate text-xs text-muted-foreground">{row.description}</div>
                    ) : null}
                  </div>
                  <Mono>{JSON.stringify(row.value)}</Mono>
                  <div className="text-sm tabular-nums">{row.version}</div>
                  <div>
                    <Button
                      size="sm"
                      onClick={() => {
                        setEditing(row);
                        setDraft(JSON.stringify(row.value));
                      }}
                    >
                      Change
                    </Button>
                  </div>
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>

      <Modal
        open={editing !== null}
        title={editing ? `${editing.area}.${editing.key}` : ""}
        subtitle="JSON is stored as JSON. Anything else is stored as the text you type."
        width="sm"
        onClose={() => setEditing(null)}
        footer={
          <>
            <Button onClick={() => setEditing(null)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={save.busy}
              onClick={() => void save.run(editing!.key, draft, editing!.version)}
            >
              Save a new version
            </Button>
          </>
        }
      >
        <Field label="Value" required>
          <Textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
        </Field>
      </Modal>
    </div>
  );
}

/*
  Tier 1 issues without review, so a sample of what it issued is pulled every
  month and read by a person. The point is not to catch every fault, it is to
  know whether the automation is still safe to leave alone.
*/
function QualitySamples() {
  const samples = useApi<QualitySampleRow[]>("/quality-sample");
  const [reviewing, setReviewing] = React.useState<QualitySampleRow | null>(null);
  const [outcome, setOutcome] = React.useState("sound");
  const [notes, setNotes] = React.useState("");

  const review = useAction(async (id: string) => {
    await api(`/quality-sample/${id}/review${query({ outcome, notes })}`, { method: "POST" });
    samples.reload();
    setReviewing(null);
    setNotes("");
  });

  const rows = samples.data ?? [];
  const outstanding = rows.filter((row) => !row.reviewed).length;

  return (
    <div className="space-y-4">
      {outstanding ? (
        <Notice tone="warn" title={`${outstanding} sampled documents are unread`}>
          An automation that nobody checks is an automation nobody can defend. Each of these was
          issued without review, and the sample is how that stays justifiable.
        </Notice>
      ) : (
        <Notice tone="good" title="Every sampled document has been read">
          The monthly sample is clear.
        </Notice>
      )}

      {review.error ? (
        <Refusal title="That review was refused" reason={review.error.message} reasons={review.error.reasons} />
      ) : null}

      <Card>
        <CardHeader title="Monthly quality sample" subtitle="Documents issued by tier 1 automation" />
        <div className="table-scroll">
          <div className="min-w-[56.25rem]">
            <Row cols={SAMPLE_COLS} head>
              <div>Period</div>
              <div>Reference</div>
              <div>Why it was pulled</div>
              <div>Outcome</div>
              <div>Action</div>
            </Row>
            <DataState
              loading={samples.loading}
              errorMessage={samples.error?.message}
              isEmpty={rows.length === 0}
              emptyTitle="Nothing has been sampled yet"
            >
              {rows.map((row) => (
                <Row key={row.id} cols={SAMPLE_COLS}>
                  <div className="text-sm">{row.period}</div>
                  <Mono>{row.object_reference}</Mono>
                  <div className="min-w-0 truncate text-sm text-muted-foreground">{row.reason}</div>
                  <div>
                    {row.outcome ? (
                      <Pill tone={row.outcome === "sound" ? "good" : "warn"}>
                        {titleCase(row.outcome)}
                      </Pill>
                    ) : (
                      <Pill tone="neutral">Unread</Pill>
                    )}
                  </div>
                  <div>
                    {row.reviewed ? (
                      <span className="text-xs text-muted-foreground">{row.notes ?? "Read"}</span>
                    ) : (
                      <Button size="sm" onClick={() => setReviewing(row)}>
                        Review
                      </Button>
                    )}
                  </div>
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>

      <Modal
        open={reviewing !== null}
        title={reviewing ? `Review ${reviewing.object_reference}` : ""}
        subtitle="Sound, a minor issue, or a material issue. A material issue is a reason to reconsider the tier 1 rule itself."
        width="sm"
        onClose={() => setReviewing(null)}
        footer={
          <>
            <Button onClick={() => setReviewing(null)}>Cancel</Button>
            <Button variant="primary" disabled={review.busy} onClick={() => void review.run(reviewing!.id)}>
              Record the review
            </Button>
          </>
        }
      >
        <Field label="Outcome" required>
          <Select value={outcome} onChange={(event) => setOutcome(event.target.value)}>
            {SAMPLE_OUTCOMES.map((value) => (
              <option key={value} value={value}>
                {titleCase(value)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Notes">
          <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
        </Field>
      </Modal>
    </div>
  );
}

export default function Administration() {
  const { entity } = useSession();
  const [tab, setTab] = React.useState("retention");

  return (
    <div className="space-y-6">
      <PageTitle
        title="Administration"
        subtitle={`Retention, the data boundary, connectors, people and the audit trail. Entity ${entity}.`}
      />

      <Tabs
        tabs={[
          { id: "retention", label: "Retention and holds" },
          { id: "boundary", label: "Export and deletion" },
          { id: "connectors", label: "Connectors" },
          { id: "people", label: "People" },
          { id: "organisation", label: "Organisation" },
          { id: "config", label: "Configuration" },
          { id: "security", label: "Your security" },
          { id: "quality", label: "Quality sample" },
          { id: "audit", label: "Audit" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "retention" ? <Retention /> : null}
      {tab === "boundary" ? <Boundary /> : null}
      {tab === "connectors" ? <Connectors /> : null}
      {tab === "people" ? <People /> : null}
      {tab === "organisation" ? <Organisations /> : null}
      {tab === "config" ? <Configuration /> : null}
      {tab === "security" ? <MfaEnrolment /> : null}
      {tab === "quality" ? <QualitySamples /> : null}
      {tab === "audit" ? <Audit /> : null}
    </div>
  );
}
