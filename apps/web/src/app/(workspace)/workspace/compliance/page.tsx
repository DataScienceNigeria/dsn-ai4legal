"use client";

import * as React from "react";

import { useRoles, useSession } from "@/components/app/session";
import {
  Button,
  Card,
  CardHeader,
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
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { ComplianceItem } from "@/lib/types";
import { formatDate, titleCase } from "@/lib/utils";

const COLS = "minmax(0,1.5fr) 8.125rem 8.125rem 6.875rem minmax(0,1fr) 6.875rem";

const RECURRENCES = ["annual", "biannual", "quarterly", "monthly", "one_off", "event_driven"];

function daysUntil(due: string): number {
  return Math.round((new Date(due).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
}

function isOverdue(item: ComplianceItem): boolean {
  return (
    item.status === "open" &&
    item.next_due_date !== null &&
    new Date(item.next_due_date).getTime() < Date.now()
  );
}

function DueCell({ item }: Readonly<{ item: ComplianceItem }>) {
  if (item.next_due_date === null) return <Pill tone="neutral">No date set</Pill>;
  const days = daysUntil(item.next_due_date);
  if (days < 0) return <Pill tone="bad">{`${Math.abs(days)} days overdue`}</Pill>;
  if (days <= item.lead_time_days) return <Pill tone="warn">{`In ${days} days`}</Pill>;
  return <span className="text-xs text-muted-foreground">{formatDate(item.next_due_date)}</span>;
}

function RecordedFiling({ item }: Readonly<{ item: ComplianceItem }>) {
  return (
    <div className="text-xs text-muted-foreground">
      {item.evidence_reference === null ? (
        <span className="text-warning">No evidence recorded</span>
      ) : (
        <span>{item.evidence_reference}</span>
      )}
      {item.filing_number ? <div>{item.filing_number}</div> : null}
    </div>
  );
}

/*
  A statutory requirement changes. The old version is not edited, because a
  filing made last year was made against last year's rule, and the record has
  to keep saying which rule that was.
*/
function RequirementVersion({
  item,
  onDone,
}: Readonly<{ item: ComplianceItem; onDone: () => void }>) {
  const { has } = useRoles();
  const [open, setOpen] = React.useState(false);
  const history = useApi<ComplianceItem[]>(open ? `/compliance/${item.id}/history` : null, [
    item.id,
    open,
  ]);

  const [effective, setEffective] = React.useState("");
  const [requirement, setRequirement] = React.useState("");
  const [reference, setReference] = React.useState("");
  const [recurrence, setRecurrence] = React.useState("");
  const [nextDue, setNextDue] = React.useState("");
  const [leadTime, setLeadTime] = React.useState("");

  const version = useAction(async () => {
    await api(`/compliance/${item.id}/versions`, {
      method: "POST",
      body: {
        effective_date: effective,
        requirement: requirement || undefined,
        statutory_reference: reference || undefined,
        recurrence: recurrence || undefined,
        next_due_date: nextDue || undefined,
        lead_time_days: leadTime ? Number(leadTime) : undefined,
      },
    });
    onDone();
    history.reload();
    setEffective("");
  });

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Versions
      </Button>
      <Modal
        open={open}
        title={item.requirement}
        subtitle="Every version is kept, and each filing points at the version that applied when it was made."
        width="lg"
        onClose={() => setOpen(false)}
      >
        <div>
          <div className="mb-2 text-sm font-semibold">History</div>
          <DataState
            loading={history.loading}
            errorMessage={history.error?.message}
            isEmpty={(history.data ?? []).length === 0}
            emptyTitle="Only the current version exists"
          >
            <div className="space-y-2">
              {(history.data ?? []).map((row) => (
                <div key={row.id} className="flex flex-wrap items-center gap-2 rounded-md border p-3">
                  <Pill tone={row.status === "superseded" ? "neutral" : "good"}>
                    {`v${row.version}, ${titleCase(row.status)}`}
                  </Pill>
                  <span className="text-xs text-muted-foreground">
                    {`Effective ${formatDate(row.effective_date)}`}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm">{row.requirement}</span>
                </div>
              ))}
            </div>
          </DataState>
        </div>

        {has("privacy", "head_of_legal", "legal_ops", "admin") ? (
          <div className="space-y-3 rounded-md border p-4">
            <div className="text-sm font-semibold">Publish a new version</div>
            <p className="text-sm text-muted-foreground">
              The current version is superseded from the effective date. Anything left blank
              carries over unchanged.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Effective from" required>
                <Input
                  type="date"
                  value={effective}
                  onChange={(event) => setEffective(event.target.value)}
                />
              </Field>
              <Field label="Next due">
                <Input type="date" value={nextDue} onChange={(event) => setNextDue(event.target.value)} />
              </Field>
              <Field label="Requirement">
                <Input value={requirement} onChange={(event) => setRequirement(event.target.value)} />
              </Field>
              <Field label="Statutory reference">
                <Input value={reference} onChange={(event) => setReference(event.target.value)} />
              </Field>
              <Field label="Recurrence">
                <Select value={recurrence} onChange={(event) => setRecurrence(event.target.value)}>
                  <option value="">Unchanged</option>
                  {RECURRENCES.map((value) => (
                    <option key={value} value={value}>
                      {titleCase(value)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Lead time, days">
                <Input
                  type="number"
                  value={leadTime}
                  onChange={(event) => setLeadTime(event.target.value)}
                />
              </Field>
            </div>
            {version.error ? (
              <Refusal title="That version was refused" reason={version.error.message} />
            ) : null}
            <Button variant="primary" disabled={!effective || version.busy} onClick={() => void version.run()}>
              Publish the version
            </Button>
          </div>
        ) : null}
      </Modal>
    </>
  );
}

export default function Compliance() {
  const { entity } = useSession();
  const [tab, setTab] = React.useState("due");
  const [evidence, setEvidence] = React.useState<Record<string, string>>({});
  const [filing, setFiling] = React.useState<Record<string, string>>({});

  const all = useApi<ComplianceItem[]>("/compliance", [entity]);

  const items = all.data ?? [];
  const rows = React.useMemo(() => {
    if (tab === "completed") return items.filter((item) => item.status === "completed");
    if (tab === "superseded") return items.filter((item) => item.status === "superseded");
    if (tab === "overdue") return items.filter(isOverdue);
    return items.filter((item) => item.status === "open");
  }, [items, tab]);

  const complete = useAction(async (id: string) => {
    await api(`/compliance/${id}/complete`, {
      method: "POST",
      body: {
        evidence_reference: evidence[id] ?? null,
        filing_number: filing[id] ?? null,
      },
    });
    all.reload();
  });

  const evidenceGaps = items.filter(
    (item) =>
      item.status === "completed" && item.evidence_required && item.evidence_reference === null,
  ).length;

  const counts = {
    due: items.filter((item) => item.status === "open").length,
    overdue: items.filter(isOverdue).length,
    completed: items.filter((item) => item.status === "completed").length,
    superseded: items.filter((item) => item.status === "superseded").length,
  };

  return (
    <div className="space-y-6">
      <PageTitle
        title="Compliance calendar"
        subtitle={
          "Statutory filings with an accountable owner, the evidence each one needs, and the " +
          "version of the requirement that applied at the time."
        }
      />

      {evidenceGaps > 0 ? (
        <Notice tone="warn" title={`${evidenceGaps} completed filings have no evidence`}>
          A filing recorded as done without its evidence cannot be shown to a board or a funder.
        </Notice>
      ) : null}

      <Tabs
        tabs={[
          { id: "due", label: "Due", badge: counts.due },
          { id: "overdue", label: "Overdue", badge: counts.overdue },
          { id: "completed", label: "Completed", badge: counts.completed },
          { id: "superseded", label: "Superseded", badge: counts.superseded },
        ]}
        active={tab}
        onChange={setTab}
      />

      {complete.error ? (
        <Refusal title="That filing was not recorded" reason={complete.error.message} />
      ) : null}

      <Card>
        <CardHeader title={`${rows.length} items`} subtitle={`Entity ${entity}`} />
        <div className="table-scroll">
          <div className="min-w-[69rem]">
            <Row cols={COLS} head>
              <div>Requirement</div>
              <div>Recurrence</div>
              <div>Next due</div>
              <div>Version</div>
              <div>Evidence and filing</div>
              <div>Versions</div>
            </Row>

            <DataState
              loading={all.loading}
              errorMessage={all.error?.message}
              errorTitle="The calendar is not available to you"
              isEmpty={rows.length === 0}
            >
              {rows.map((item) => (
                <Row key={item.id} cols={COLS}>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{item.requirement}</div>
                    {item.statutory_reference ? <Mono>{item.statutory_reference}</Mono> : null}
                    <div className="mt-0.5 text-xs text-muted-foreground">{item.jurisdiction}</div>
                  </div>
                  <div className="text-sm">{titleCase(item.recurrence)}</div>
                  <div>
                    <DueCell item={item} />
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {`v${item.version}`}
                    {item.effective_date ? (
                      <div>{`From ${formatDate(item.effective_date)}`}</div>
                    ) : null}
                  </div>
                  <div>
                    {item.status === "open" ? (
                      <div className="flex flex-wrap items-end gap-2">
                        <Field
                          label={item.evidence_required ? "Evidence, required" : "Evidence"}
                        >
                          <Input
                            value={evidence[item.id] ?? ""}
                            onChange={(event) =>
                              setEvidence({ ...evidence, [item.id]: event.target.value })
                            }
                            placeholder="Link or reference"
                          />
                        </Field>
                        <Field label="Filing number">
                          <Input
                            value={filing[item.id] ?? ""}
                            onChange={(event) =>
                              setFiling({ ...filing, [item.id]: event.target.value })
                            }
                            placeholder="Optional"
                          />
                        </Field>
                        <Button
                          size="sm"
                          disabled={complete.busy}
                          onClick={() => complete.run(item.id)}
                        >
                          Record filing
                        </Button>
                      </div>
                    ) : (
                      <RecordedFiling item={item} />
                    )}
                  </div>
                  <div>
                    <RequirementVersion item={item} onDone={() => all.reload()} />
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
