"use client";

import * as React from "react";

import { Icon, type IconName } from "@/components/app/icons";
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
  KeyValue,
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
  EgressRow,
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
const CONNECTOR_COLS =
  "minmax(0,1.5fr) 6.25rem 12.5rem 8.75rem 10rem 4.375rem";
const PEOPLE_COLS = "minmax(0,1.2fr) minmax(0,1.1fr) 5.625rem minmax(0,1fr) 7.5rem 8.125rem";
const PEOPLE_COLS_WRITE =
  "minmax(0,1.2fr) minmax(0,1.1fr) 5.625rem minmax(0,1fr) 7.5rem 8.125rem 9.375rem";
const SAMPLE_COLS = "7.5rem 9.375rem minmax(0,1fr) 8.125rem 9.375rem";


const SAMPLE_OUTCOMES = ["sound", "minor_issue", "material_issue"];
const AUDIT_COLS = "10.625rem 10rem minmax(0,1fr) minmax(0,13rem) 5.625rem";

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
        <CardHeader
          title="Request a bulk export"
          subtitle="Somebody else approves it. Restricted content is never included, whoever asks."
        />
        <CardBody>
          <div className="grid gap-4 sm:grid-cols-[12rem_minmax(0,1fr)]">
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
            <Field label="Reason" required>
              <Textarea
                rows={2}
                value={form.reason}
                onChange={(event) => setForm({ ...form, reason: event.target.value })}
                placeholder="What the export is for and who asked for it"
              />
            </Field>
          </div>
          <div className="mt-4 flex items-center justify-between gap-3 border-t pt-4">
            <p className="text-xs text-muted-foreground">
              Internal and below. Five export requests a day, per person.
            </p>
            <Button
              variant="primary"
              disabled={requestExport.busy || form.reason.trim() === ""}
              onClick={() => requestExport.run()}
            >
              {requestExport.busy ? "Requesting" : "Request the export"}
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

const EGRESS_COLS = "11.25rem 10rem minmax(0,1fr) 8.125rem 7.5rem";

function ReviewDate({ value }: Readonly<{ value: string | null }>) {
  if (value === null) {
    return <span className="text-xs text-muted-foreground">Never reviewed</span>;
  }
  const overdue = new Date(value).getTime() < Date.now();
  return (
    <Pill tone={overdue ? "warn" : "neutral"}>
      {overdue ? `Due ${formatDateTime(value)}` : formatDateTime(value)}
    </Pill>
  );
}

/*
  Registration is a deployment act, not a screen. A connector is code that
  knows how to talk to something, and a row added here would name a route
  nothing can travel. What a register answers is the opposite question, and
  that one belongs on a screen: what routes exist, who owns each, what each may
  carry, when somebody last looked at it, and what has actually gone through.
*/
function Connectors() {
  const connectors = useApi<ConnectorRow[]>("/connectors");
  const [chosen, setChosen] = React.useState("");
  const egress = useApi<EgressRow[]>(
    `/connectors/egress${chosen ? `?connector=${encodeURIComponent(chosen)}` : ""}`,
    [chosen],
  );
  const rows = connectors.data ?? [];
  const sent = egress.data ?? [];

  return (
    <div className="space-y-4">
      <Notice tone="info" title="A route has to exist here before anything travels it">
        Each connector is code that knows how to talk to one thing, so they arrive with a
        deployment rather than from this screen. What the register answers is which routes exist,
        who owns each, and what each may carry.
      </Notice>

      <Card>
        <CardHeader
          title="Every route in and out of the platform"
          subtitle="A connector that is not registered here cannot carry anything anywhere."
        />
        <div className="table-scroll">
          <div className="min-w-[68rem]">
            <Row cols={CONNECTOR_COLS} head>
              <div>Connector</div>
              <div>Direction</div>
              <div>Permitted classes</div>
              <div>Owner</div>
              <div>Next review</div>
              <div>Calls</div>
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
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">{row.name}</span>
                      {row.active ? null : <Pill tone="neutral">Off</Pill>}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">{row.purpose}</div>
                    {row.scopes.length > 0 ? (
                      <div className="mt-1 truncate text-xs text-muted-foreground/80">
                        {row.scopes.join(", ")}
                      </div>
                    ) : null}
                  </div>
                  <div className="text-sm">{titleCase(row.direction)}</div>
                  <div className="flex flex-wrap gap-1">
                    {row.permitted_data_classes.map((value) => (
                      <Pill key={value} tone={value === "restricted" ? "bad" : "neutral"}>
                        {titleCase(value)}
                      </Pill>
                    ))}
                  </div>
                  <div className="truncate text-sm">
                    {row.owner ?? <span className="text-muted-foreground">Unowned</span>}
                  </div>
                  <div>
                    <ReviewDate value={row.review_date} />
                  </div>
                  <div>
                    <button
                      type="button"
                      className="text-sm tabular-nums underline-offset-2 hover:underline"
                      onClick={() => setChosen(chosen === row.code ? "" : row.code)}
                    >
                      {row.calls}
                    </button>
                  </div>
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="What actually went through them"
          subtitle="The register says what a route may carry. This says what it carried."
          actions={
            <Select value={chosen} onChange={(event) => setChosen(event.target.value)}>
              <option value="">All connectors</option>
              {rows.map((row) => (
                <option key={row.code} value={row.code}>
                  {row.name}
                </option>
              ))}
            </Select>
          }
        />
        <div className="table-scroll">
          <div className="min-w-[56rem]">
            <Row cols={EGRESS_COLS} head>
              <div>When</div>
              <div>Connector</div>
              <div>Purpose</div>
              <div>Class</div>
              <div>Result</div>
            </Row>
            <DataState
              loading={egress.loading}
              errorMessage={egress.error?.message}
              errorTitle="The egress log is not available to you"
              isEmpty={sent.length === 0}
              emptyTitle="Nothing has travelled this route"
              emptyDetail="Every outbound call writes a line here as it is made."
            >
              {sent.map((row) => (
                <Row key={row.id} cols={EGRESS_COLS}>
                  <div className="text-xs text-muted-foreground">
                    {formatDateTime(row.occurred_at)}
                  </div>
                  <Mono>{row.connector_code}</Mono>
                  <div className="min-w-0">
                    <div className="truncate text-sm">{row.purpose}</div>
                    {row.record_reference ? <Mono>{row.record_reference}</Mono> : null}
                  </div>
                  <div className="text-sm">{titleCase(row.data_class)}</div>
                  <div>
                    <Pill tone={row.result === "success" ? "good" : "bad"}>
                      {titleCase(row.result)}
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
      <IconButton
        icon="shield"
        tone="destructive"
        label={`Reset the second factor for ${user.name}`}
        onClick={() => setOpen(true)}
      />
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

/*
  Four actions per person, and each label longer than the button. Icons with a
  tooltip and an accessible name, because the row is what people scan and five
  words of chrome on every row is what stopped them scanning it.
*/
function IconButton({
  icon,
  label,
  tone = "default",
  disabled,
  onClick,
}: Readonly<{
  icon: IconName;
  label: string;
  tone?: "default" | "destructive" | "primary";
  disabled?: boolean;
  onClick: () => void;
}>) {
  return (
    <Button
      size="sm"
      variant={tone === "default" ? "ghost" : tone}
      className="h-8 w-8 border-border px-0"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
    >
      <Icon name={icon} className="h-4 w-4" />
    </Button>
  );
}

/*
  The five practice areas the platform issues matter numbers under. A
  specialism is one of these, and a matter opening in that area proposes the
  people who hold it before anybody else.
*/
const SPECIALISMS: { code: string; label: string }[] = [
  { code: "com", label: "Commercial" },
  { code: "emp", label: "Employment" },
  { code: "ipr", label: "Intellectual property" },
  { code: "dpr", label: "Data protection" },
  { code: "crp", label: "Corporate" },
];

function SpecialismChoice({
  value,
  onChange,
}: Readonly<{ value: string[]; onChange: (next: string[]) => void }>) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {SPECIALISMS.map((one) => {
        const held = value.includes(one.code);
        return (
          <button
            key={one.code}
            type="button"
            onClick={() =>
              onChange(held ? value.filter((c) => c !== one.code) : [...value, one.code])
            }
            className={cn(
              "rounded-full border px-2.5 py-1 text-xs transition-colors",
              held
                ? "border-primary bg-primary/15 text-foreground"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {one.label}
          </button>
        );
      })}
    </div>
  );
}

function specialismLabels(codes: string[]): string {
  return codes
    .map((code) => SPECIALISMS.find((one) => one.code === code)?.label ?? titleCase(code))
    .join(", ");
}

const ASSIGNABLE_ROLES = [
  "requester",
  "counsel",
  "head_of_legal",
  "finance",
  "procurement",
  "management",
  "auditor",
  "consultant",
  "admin",
];

const ENTITIES = ["DSN", "EAI"];

/*
  Entity membership is the hard boundary, so it is offered as the three
  answers there are rather than as a pair of checkboxes somebody can leave
  empty. Reach is the intersection of role and entity, never the wider of
  them: a person left on DSN alone cannot open an EAI matter whatever their
  role says.
*/
function EntityChoice({
  value,
  onChange,
}: Readonly<{ value: string[]; onChange: (next: string[]) => void }>) {
  const current = value.length === 2 ? "both" : (value[0] ?? "DSN");
  return (
    <Select
      value={current}
      onChange={(event) =>
        onChange(event.target.value === "both" ? [...ENTITIES] : [event.target.value])
      }
    >
      <option value="DSN">DSN only</option>
      <option value="EAI">EAI only</option>
      <option value="both">Both entities</option>
    </Select>
  );
}

function RoleChoice({
  value,
  onChange,
}: Readonly<{ value: string[]; onChange: (next: string[]) => void }>) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {ASSIGNABLE_ROLES.map((role) => {
        const held = value.includes(role);
        return (
          <button
            key={role}
            type="button"
            onClick={() =>
              onChange(held ? value.filter((one) => one !== role) : [...value, role])
            }
            className={cn(
              "rounded-full border px-2.5 py-1 text-xs transition-colors",
              held
                ? "border-primary bg-primary/15 text-foreground"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {titleCase(role)}
          </button>
        );
      })}
    </div>
  );
}

/*
  Adding somebody used to mean editing the seed file, which in practice meant
  asking whoever had a terminal. The password is set here and never shown
  again: it is hashed on the way in, and the audit records that it was set
  rather than what it was.
*/
function AddPerson({ onDone }: Readonly<{ onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [form, setForm] = React.useState({
    name: "",
    work_email: "",
    roles: ["requester"] as string[],
    entities: ["DSN"] as string[],
    specialisms: [] as string[],
    workload_ceiling: "10",
    password: "",
  });

  const add = useAction(async () => {
    await api("/users", {
      method: "POST",
      body: {
        name: form.name,
        work_email: form.work_email,
        roles: form.roles,
        entities: form.entities,
        specialisms: form.specialisms,
        workload_ceiling: Number(form.workload_ceiling) || 10,
        password: form.password,
      },
    });
    onDone();
    setOpen(false);
    setForm({ ...form, name: "", work_email: "", password: "", specialisms: [] });
  });

  const ready =
    form.name.trim().length > 1 &&
    /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.work_email.trim()) &&
    form.roles.length > 0 &&
    form.password.length >= 12;

  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        Add a person
      </Button>
      <Modal
        open={open}
        title="Add a person"
        subtitle="Roles say what they may do. Entities say where. Reach is the intersection, never the wider of the two."
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={!ready || add.busy} onClick={() => void add.run()}>
              {add.busy ? "Adding" : "Add them"}
            </Button>
          </>
        }
      >
        {add.error ? (
          <Refusal
            title="That person was not added"
            reason={add.error.message}
            reasons={Object.values(add.error.fieldErrors)}
          />
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" required>
            <Input
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
          <Field label="Work email" required hint="This is also how they sign in.">
            <Input
              value={form.work_email}
              onChange={(event) => setForm({ ...form, work_email: event.target.value })}
            />
          </Field>
        </div>

        <Field label="Roles" required>
          <RoleChoice value={form.roles} onChange={(roles) => setForm({ ...form, roles })} />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Entities" required>
            <EntityChoice
              value={form.entities}
              onChange={(entities) => setForm({ ...form, entities })}
            />
          </Field>
          <Field
            label="Most open matters at once"
            hint="The proposal will not put an eleventh matter on somebody set to ten."
          >
            <Input
              inputMode="numeric"
              value={form.workload_ceiling}
              onChange={(event) => setForm({ ...form, workload_ceiling: event.target.value })}
            />
          </Field>
        </div>

        <Field
          label="Practice areas"
          hint="When a matter opens in one of these, the platform proposes them as its owner before anybody else."
        >
          <SpecialismChoice
            value={form.specialisms}
            onChange={(specialisms) => setForm({ ...form, specialisms })}
          />
        </Field>

        <Field
          label="First password"
          required
          hint="At least 12 characters. You will know it, so they are expected to change it."
        >
          <Input
            type="password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
        </Field>
      </Modal>
      <StepUpGate action="Adding a person" state={add} />
    </>
  );
}

function EditPerson({
  user,
  onDone,
}: Readonly<{ user: UserRow; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [roles, setRoles] = React.useState(user.roles);
  const [entities, setEntities] = React.useState(user.entities);
  const [name, setName] = React.useState(user.name);
  const [specialisms, setSpecialisms] = React.useState(user.specialisms);
  const [ceiling, setCeiling] = React.useState(String(user.workload_ceiling));
  const [reason, setReason] = React.useState("");

  const save = useAction(async () => {
    await api(`/users/${user.id}`, {
      method: "PATCH",
      body: {
        name,
        roles,
        entities,
        specialisms,
        workload_ceiling: Number(ceiling) || user.workload_ceiling,
        reason,
      },
    });
    onDone();
    setOpen(false);
    setReason("");
  });

  return (
    <>
      <IconButton
        icon="rename"
        label={`Edit ${user.name}`}
        onClick={() => {
          setName(user.name);
          setRoles(user.roles);
          setEntities(user.entities);
          setSpecialisms(user.specialisms);
          setCeiling(String(user.workload_ceiling));
          setOpen(true);
        }}
      />
      <Modal
        open={open}
        title={`Edit ${user.name}`}
        subtitle={user.work_email}
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={roles.length === 0 || reason.trim().length < 4 || save.busy}
              onClick={() => void save.run()}
            >
              {save.busy ? "Saving" : "Save"}
            </Button>
          </>
        }
      >
        {save.error ? (
          <Refusal
            title="That change was refused"
            reason={save.error.message}
            reasons={Object.values(save.error.fieldErrors)}
          />
        ) : null}

        <Field label="Name" required>
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </Field>

        <Field label="Roles" required>
          <RoleChoice value={roles} onChange={setRoles} />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Entities" required>
            <EntityChoice value={entities} onChange={setEntities} />
          </Field>
          <Field label="Most open matters at once">
            <Input
              inputMode="numeric"
              value={ceiling}
              onChange={(event) => setCeiling(event.target.value)}
            />
          </Field>
        </div>

        <Field
          label="Practice areas"
          hint="A matter opening in one of these proposes them as its owner first."
        >
          <SpecialismChoice value={specialisms} onChange={setSpecialisms} />
        </Field>

        <Field label="Why" required hint="Recorded beside what it was before.">
          <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
      </Modal>
      <StepUpGate action="Changing what somebody reaches" state={save} />
    </>
  );
}

function SetPassword({ user, onDone }: Readonly<{ user: UserRow; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [password, setPassword] = React.useState("");
  const [reason, setReason] = React.useState("");

  const save = useAction(async () => {
    await api(`/users/${user.id}/password`, {
      method: "POST",
      body: { password, reason },
    });
    onDone();
    setOpen(false);
    setPassword("");
    setReason("");
  });

  return (
    <>
      <IconButton
        icon="key"
        label={`Set a password for ${user.name}`}
        onClick={() => setOpen(true)}
      />
      <Modal
        open={open}
        title={`Set a password for ${user.name}`}
        subtitle="You will know this password, so it is a reset and not a recovery. They are expected to change it, and the act is on the audit under both names."
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={password.length < 12 || reason.trim().length < 4 || save.busy}
              onClick={() => void save.run()}
            >
              {save.busy ? "Setting" : "Set it"}
            </Button>
          </>
        }
      >
        {save.error ? (
          <Refusal title="It was not set" reason={save.error.message} />
        ) : null}
        <Field label="New password" required hint="At least 12 characters.">
          <Input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>
        <Field label="Why" required>
          <Input value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
      </Modal>
      <StepUpGate action="Setting somebody's password" state={save} />
    </>
  );
}

/*
  Suspension bites on the next request rather than the next sign-in: the
  active flag is read when a token is turned into a principal, so a session
  already open stops at its next call. Nothing is ever deleted, because the
  record is on decisions, approvals and the audit chain.
*/
function Suspend({ user, onDone }: Readonly<{ user: UserRow; onDone: () => void }>) {
  const { me } = useSession();
  const [open, setOpen] = React.useState(false);

  const change = useAction(async (reason: string) => {
    await api(`/users/${user.id}/status`, {
      method: "POST",
      body: { active: !user.active, reason },
    });
    onDone();
    setOpen(false);
  });

  if (user.id === me?.id) return null;

  return (
    <>
      <IconButton
        icon={user.active ? "suspend" : "reinstate"}
        tone={user.active ? "destructive" : "primary"}
        label={user.active ? `Suspend ${user.name}` : `Reinstate ${user.name}`}
        onClick={() => setOpen(true)}
      />
      <Confirm
        open={open}
        title={user.active ? `Suspend ${user.name}` : `Reinstate ${user.name}`}
        detail={
          user.active
            ? "They stop at their next request, not at their next sign-in. Nothing of theirs is deleted, and their name stays on every decision they made."
            : "They can sign in again with the password they already have."
        }
        confirmLabel={user.active ? "Suspend them" : "Reinstate them"}
        destructive={user.active}
        reasonLabel="Why"
        busy={change.busy}
        error={change.error?.message}
        onCancel={() => setOpen(false)}
        onConfirm={(reason: string) => void change.run(reason)}
      />
      <StepUpGate action="Suspending or reinstating somebody" state={change} />
    </>
  );
}

function People() {
  const { has } = useRoles();
  const canWrite = has("admin", "head_of_legal");
  const users = useApi<UserRow[]>("/users");
  const rows = users.data ?? [];
  const cols = canWrite ? PEOPLE_COLS_WRITE : PEOPLE_COLS;

  return (
    <div className="space-y-4">
      <Notice tone="info" title="Reach is role and entity together">
        A role says what somebody may do, an entity says where, and somebody on DSN alone cannot
        open an EAI matter. Nobody is deleted: suspension stops them at their next request and
        leaves their name on the work they did.
      </Notice>

      <Card>
        <CardHeader
          title="People and effective permission"
          subtitle="Permission is the intersection of role, entity and matter access."
          actions={canWrite ? <AddPerson onDone={() => users.reload()} /> : null}
        />
        <div className="table-scroll">
          <div className={canWrite ? "min-w-[70rem]" : "min-w-[56rem]"}>
            <Row cols={cols} head>
              <div>Name</div>
              <div>Roles</div>
              <div>Entities</div>
              <div>Practice areas</div>
              <div>Open matters</div>
              <div>Second factor</div>
              {canWrite ? <div>Actions</div> : null}
            </Row>
            <DataState
              loading={users.loading}
              errorMessage={users.error?.message}
              errorTitle="People are not available to you"
              isEmpty={rows.length === 0}
              emptyTitle="No person is registered"
            >
              {rows.map((user) => (
                <Row key={user.id} cols={cols}>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">{user.name}</span>
                      {user.active ? null : <Pill tone="bad">Suspended</Pill>}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {user.work_email}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {user.roles.map((role) => (
                      <Pill key={role} tone="neutral">
                        {titleCase(role)}
                      </Pill>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {user.entities.map((entity) => (
                      <span
                        key={entity}
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs",
                          entityTone(entity).chip,
                        )}
                      >
                        {entity}
                      </span>
                    ))}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {user.specialisms.length > 0
                      ? specialismLabels(user.specialisms)
                      : "None recorded"}
                  </div>
                  <div className="text-sm">
                    <Pill tone={user.workload >= user.workload_ceiling ? "warn" : "neutral"}>
                      {`${user.workload} of ${user.workload_ceiling}`}
                    </Pill>
                  </div>
                  <div>
                    <Pill tone={user.mfa_enrolled ? "good" : "neutral"}>
                      {user.mfa_enrolled ? "Enrolled" : "Not enrolled"}
                    </Pill>
                  </div>
                  {canWrite ? (
                    <div className="flex items-center gap-1.5">
                      <EditPerson user={user} onDone={() => users.reload()} />
                      <SetPassword user={user} onDone={() => users.reload()} />
                      <ResetSecondFactor user={user} onDone={() => users.reload()} />
                      <Suspend user={user} onDone={() => users.reload()} />
                    </div>
                  ) : null}
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>
    </div>
  );
}

function fieldText(value: unknown): string {
  if (value === null || value === undefined) return "nothing";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/*
  What changed, rather than two objects side by side. A reader looking at an
  audit row is asking one question, what is different, and answering it with
  the whole before and the whole after makes them do the diff themselves on
  the row where it matters most.
*/
function Changes({
  before,
  after,
}: Readonly<{
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}>) {
  const keys = Array.from(
    new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]),
  ).filter((key) => fieldText(before?.[key]) !== fieldText(after?.[key]));

  if (keys.length === 0) {
    return <p className="text-xs text-muted-foreground">No field-level state was recorded.</p>;
  }

  return (
    <div className="space-y-1.5">
      {keys.map((key) => (
        <div key={key} className="grid gap-1 sm:grid-cols-[10rem_minmax(0,1fr)]">
          <div className="text-xs font-medium">{titleCase(key)}</div>
          <div className="min-w-0 text-xs">
            {before && key in before ? (
              <span className="break-words text-muted-foreground line-through">
                {fieldText(before[key])}
              </span>
            ) : null}
            {before && key in before ? <span className="px-1.5 text-muted-foreground">to</span> : null}
            <span className="break-words">{fieldText(after?.[key])}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

/*
  The row holds fourteen columns and the table has room for five. The rest are
  the ones that answer what changed, from where, and whether this row can be
  trusted, so they open underneath rather than living in a file nobody opens.
*/
function AuditDetail({ event }: Readonly<{ event: AuditRow }>) {
  return (
    <div className="border-b bg-muted/30 px-4 py-3">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            What changed
          </div>
          <Changes before={event.before_state} after={event.after_state} />
          {event.detail ? (
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{event.detail}</p>
          ) : null}
        </div>
        <div className="space-y-1.5 text-xs">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Where it came from, and where it sits
          </div>
          <KeyValue
            rows={[
              ["Address", event.ip_address ?? "Not recorded"],
              ["Session", event.session_id ?? "Not recorded"],
              ["Entity", event.entity ?? "None"],
              ["Position", `#${event.sequence}`],
            ]}
          />
          <div>
            <div className="text-muted-foreground">Digest</div>
            <Mono className="block break-all">{event.digest}</Mono>
          </div>
          <div>
            <div className="text-muted-foreground">Follows</div>
            <Mono className="block break-all">{event.previous_digest ?? "Nothing, this is the first row"}</Mono>
          </div>
        </div>
      </div>
    </div>
  );
}

function isoDay(offsetDays: number): string {
  const day = new Date();
  day.setDate(day.getDate() + offsetDays);
  return day.toISOString().slice(0, 10);
}

/*
  The ranges people actually ask for. A date pair answers anything else, and
  All is first and the default so the first question a reader has of a trail,
  is the thing I am looking for in here at all, is answerable before they have
  narrowed anything.
*/
const AUDIT_RANGES = [
  { id: "all", label: "All" },
  { id: "today", label: "Today" },
  { id: "7", label: "Last 7 days" },
  { id: "30", label: "Last 30 days" },
  { id: "custom", label: "Between" },
];

function Audit() {
  const [search, setSearch] = React.useState("");
  const [opened, setOpened] = React.useState<string | null>(null);
  const [range, setRange] = React.useState("all");
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");

  const bounds = React.useMemo(() => {
    if (range === "today") return { from_date: isoDay(0), to_date: isoDay(0) };
    if (range === "7") return { from_date: isoDay(-6), to_date: isoDay(0) };
    if (range === "30") return { from_date: isoDay(-29), to_date: isoDay(0) };
    if (range === "custom") {
      return { from_date: from || undefined, to_date: to || undefined };
    }
    return {};
  }, [range, from, to]);

  const filter = query({ q: search.trim() || undefined, ...bounds });
  const events = useApi<AuditRow[]>(`/audit/events${filter}`, [filter]);
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
    await download(`/audit/events.csv${filter}`, `audit-${stamp}.csv`);
  });

  return (
    <div className="space-y-4">
      {verify.data ? (
        <Notice
          tone={verify.data.reconciled ? "good" : "warn"}
          title="The audit trail is append-only and administrators cannot alter it"
        >
          {verify.data.message} Every row carries the digest of the one before it, so a row
          removed or edited breaks the chain from that point on and this check says where.
        </Notice>
      ) : null}

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b p-3">
          <Input
            className="min-w-[14rem] flex-1"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search actor, action, object or detail"
          />
          <Select
            className="w-auto"
            value={range}
            onChange={(event) => setRange(event.target.value)}
          >
            {AUDIT_RANGES.map((one) => (
              <option key={one.id} value={one.id}>
                {one.label}
              </option>
            ))}
          </Select>
          {range === "custom" ? (
            <>
              <Input
                type="date"
                className="w-auto"
                value={from}
                onChange={(event) => setFrom(event.target.value)}
              />
              <Input
                type="date"
                className="w-auto"
                value={to}
                onChange={(event) => setTo(event.target.value)}
              />
            </>
          ) : null}
          <Button disabled={save.busy} onClick={() => void save.run()}>
            <Icon name="archive" className="h-4 w-4" />
            {save.busy ? "Preparing" : "Export CSV"}
          </Button>
        </div>
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
                <React.Fragment key={event.id}>
                  <Row cols={AUDIT_COLS}>
                    <button
                      type="button"
                      className="text-left text-xs text-muted-foreground underline-offset-2 hover:underline"
                      title="Open the full record"
                      onClick={() => setOpened(opened === event.id ? null : event.id)}
                    >
                      {formatDateTime(event.occurred_at)}
                    </button>
                    <div className="truncate text-sm">{event.actor_label}</div>
                    <div className="min-w-0">
                      <div className="truncate text-sm">{event.action.replaceAll("_", " ")}</div>
                      {event.detail ? (
                        <div className="truncate text-xs text-muted-foreground">
                          {event.detail}
                        </div>
                      ) : null}
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-xs">{event.object_type}</div>
                      {event.object_id ? (
                        <Mono className="block truncate" title={event.object_id}>
                          {event.object_id}
                        </Mono>
                      ) : null}
                    </div>
                    <div>
                      <Pill tone={event.result === "success" ? "neutral" : "bad"}>
                        {titleCase(event.result)}
                      </Pill>
                    </div>
                  </Row>
                  {opened === event.id ? <AuditDetail event={event} /> : null}
                </React.Fragment>
              ))}
            </DataState>
          </div>
        </div>
      </Card>
    </div>
  );
}

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
      {tab === "security" ? <MfaEnrolment /> : null}
      {tab === "quality" ? <QualitySamples /> : null}
      {tab === "audit" ? <Audit /> : null}
    </div>
  );
}
