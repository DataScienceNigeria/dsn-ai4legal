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
import type { ComplianceItem, UserRow } from "@/lib/types";
import { cn, formatDate, titleCase } from "@/lib/utils";

const COLS = "minmax(0,2.2fr) 6.5rem 9.5rem minmax(0,1fr) minmax(0,1.1fr) 13rem";

const RECURRENCES = ["annual", "biannual", "quarterly", "monthly", "one_off", "event_driven"];

/* What the next occurrence is called, for the ones that have a next occurrence
   at all. A one-off filing and one triggered by an event do not roll forward,
   and saying they will is worse than saying nothing. */
const ROLLS_FORWARD: Record<string, string> = {
  monthly: "month",
  quarterly: "quarter",
  biannual: "half year",
  annual: "year",
};

function plural(count: number, one: string, many: string): string {
  return count === 1 ? one : many;
}

/* Mirrors the server. Only for showing the window on the form before the item
   exists; every rendered row uses the value the server sent with it. */
const PERIOD_DAYS: Record<string, number> = {
  monthly: 30,
  quarterly: 91,
  biannual: 182,
  annual: 365,
};

function windowFor(recurrence: string, leadTime: number): number {
  const period = PERIOD_DAYS[recurrence];
  return period === undefined ? leadTime : Math.ceil(period * 0.15);
}

function daysUntil(due: string): number {
  const midnight = new Date();
  midnight.setHours(0, 0, 0, 0);
  return Math.round((new Date(`${due}T00:00:00`).getTime() - midnight.getTime()) / 86_400_000);
}

/*
  The due day is already overdue.

  A deadline is not a day you have; it is a day by which. A filing still sitting
  open on the morning it is due is late in every sense the regulator cares
  about, and a calendar that waits until tomorrow to say so gives the team its
  last warning after the last chance.
*/
function isOverdue(item: ComplianceItem): boolean {
  return item.status === "open" && item.next_due_date !== null && daysUntil(item.next_due_date) <= 0;
}

/*
  Due soon is a share of the filing's own cycle, not a fixed number of days.

  Thirty days out is most of the month for a monthly return and barely worth
  saying for an annual one, so the window is fifteen per cent of the period:
  five days on a monthly filing, fifty-five on an annual. The server works it
  out and sends it, so this page and the sidebar badge cannot disagree.
*/
function isDueSoon(item: ComplianceItem): boolean {
  if (item.status !== "open" || item.next_due_date === null) return false;
  const days = daysUntil(item.next_due_date);
  return days > 0 && days <= item.due_soon_days;
}

/*
  The date and how near it is, together.

  It used to be one or the other: a pill saying "In 12 days" with no date, or a
  date with nothing saying it was close. A filing calendar is read for both at
  once, and someone deciding what to do this week needs the urgency; someone
  putting it in a diary needs the day.
*/
function DueCell({ item }: Readonly<{ item: ComplianceItem }>) {
  if (item.next_due_date === null) {
    return <Pill tone="neutral">No date set</Pill>;
  }

  const when = formatDate(item.next_due_date);
  if (item.status !== "open") {
    return <span className="text-sm text-muted-foreground">{when}</span>;
  }

  const days = daysUntil(item.next_due_date);
  const late = days <= 0;
  const soon = days > 0 && days <= item.due_soon_days;
  return (
    <div className="min-w-0">
      <div className={cn("text-sm", late && "font-medium text-destructive")}>{when}</div>
      <div
        className={cn(
          "text-xs",
          late ? "text-destructive" : soon ? "text-warning" : "text-muted-foreground",
        )}
      >
        {days === 0
          ? "Due today"
          : late
            ? `${Math.abs(days)} days overdue`
            : `In ${days} days`}
      </div>
    </div>
  );
}

/*
  Whether the receipt exists, not whether the box was ticked.

  The point of the module is that "we filed it" is worth nothing to a board and
  the acknowledgement is worth everything, so the column says which of the two
  this row has.
*/
function EvidenceCell({ item }: Readonly<{ item: ComplianceItem }>) {
  if (item.status === "open") {
    return (
      <span className="text-xs text-muted-foreground">
        {item.evidence_required ? "Required to complete" : "Not required"}
      </span>
    );
  }

  if (item.evidence_reference === null) {
    return <Pill tone={item.evidence_required ? "bad" : "neutral"}>No evidence</Pill>;
  }

  return (
    <div className="min-w-0">
      <div className="truncate text-sm" title={item.evidence_reference}>
        {item.evidence_reference}
      </div>
      {item.filing_number ? (
        <div className="truncate text-xs text-muted-foreground">{item.filing_number}</div>
      ) : null}
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
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
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

        {has("counsel", "head_of_legal", "admin") ? (
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
              <Field label="What has to be filed">
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
              <Field label="Due soon at, days" hint="One-off and event-driven filings only.">
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

/*
  Putting an item on the calendar.

  This did not exist. The three rows the platform shipped with were the three
  rows it would ever hold, and a filing calendar that can only be added to by
  editing a seed file is a calendar the team will keep next to it in a
  spreadsheet, which is the same as not having one.

  The owner is required, not optional. Everything here ends in somebody filing
  something, and the reminder that will one day go out has to be addressed to a
  person rather than to the department in general.
*/
function AddRequirement({ onAdded }: Readonly<{ onAdded: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const users = useApi<UserRow[]>(open ? "/users" : null, [open]);

  const [requirement, setRequirement] = React.useState("");
  const [reference, setReference] = React.useState("");
  const [jurisdiction, setJurisdiction] = React.useState("Nigeria");
  const [recurrence, setRecurrence] = React.useState("annual");
  const [nextDue, setNextDue] = React.useState("");
  const [leadTime, setLeadTime] = React.useState("30");
  const [owner, setOwner] = React.useState("");
  const [evidenceRequired, setEvidenceRequired] = React.useState(true);

  const add = useAction(async () => {
    await api("/compliance", {
      method: "POST",
      body: {
        requirement: requirement.trim(),
        statutory_reference: reference.trim() || null,
        jurisdiction: jurisdiction.trim() || "Nigeria",
        recurrence,
        next_due_date: nextDue,
        lead_time_days: Number(leadTime),
        accountable_owner_id: owner,
        evidence_required: evidenceRequired,
      },
    });
    setRequirement("");
    setReference("");
    setNextDue("");
    setOwner("");
    setOpen(false);
    onAdded();
  });

  const ready = requirement.trim().length >= 5 && nextDue !== "" && owner !== "";

  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        Add an item
      </Button>
      <Modal
        open={open}
        title="Add a compliance item"
        subtitle="What is owed, who owes it, and when it falls due."
        width="lg"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={!ready || add.busy} onClick={() => void add.run()}>
              Add it
            </Button>
          </>
        }
      >
        {add.error ? (
          <Refusal
            title="That item was not added"
            reason={add.error.message}
            reasons={add.error.reasons}
          />
        ) : null}

        <Field label="What has to be filed" required hint="In the words the team uses for it.">
          <Input
            value={requirement}
            onChange={(event) => setRequirement(event.target.value)}
            placeholder="Annual return to the Corporate Affairs Commission"
          />
        </Field>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Statutory reference" hint="The section it comes from, if there is one.">
            <Input
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              placeholder="CAMA 2020, section 417"
            />
          </Field>
          <Field label="Jurisdiction">
            <Input value={jurisdiction} onChange={(event) => setJurisdiction(event.target.value)} />
          </Field>
          <Field
            label="Recurrence"
            required
            hint="One-off and event-driven do not roll forward on their own."
          >
            <Select value={recurrence} onChange={(event) => setRecurrence(event.target.value)}>
              {RECURRENCES.map((value) => (
                <option key={value} value={value}>
                  {titleCase(value)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Next due" required>
            <Input type="date" value={nextDue} onChange={(event) => setNextDue(event.target.value)} />
          </Field>
          <Field
            label="Accountable owner"
            required
            hint="Who files it. This is where the reminder will go."
          >
            <Select value={owner} onChange={(event) => setOwner(event.target.value)}>
              <option value="">Choose a person</option>
              {(users.data ?? [])
                .filter((person) => person.active)
                .map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
            </Select>
          </Field>
          {recurrence in PERIOD_DAYS ? (
            <Field label="Due soon at" hint="Fifteen per cent of the cycle, worked out for you.">
              <div className="flex h-9 items-center text-sm text-muted-foreground">
                {`${windowFor(recurrence, Number(leadTime))} days before the date`}
              </div>
            </Field>
          ) : (
            <Field
              label="Due soon at, days"
              hint="A filing with no cycle has no share to take, so name the warning yourself."
            >
              <Input
                type="number"
                min={0}
                max={365}
                value={leadTime}
                onChange={(event) => setLeadTime(event.target.value)}
              />
            </Field>
          )}
        </div>

        <Field label="Evidence" hint="A filing recorded as done with no receipt cannot be shown to anyone.">
          <div className="flex gap-2">
            <Button
              size="sm"
              variant={evidenceRequired ? "primary" : "default"}
              onClick={() => setEvidenceRequired(true)}
            >
              Required to complete
            </Button>
            <Button
              size="sm"
              variant={!evidenceRequired ? "primary" : "default"}
              onClick={() => setEvidenceRequired(false)}
            >
              Not required
            </Button>
          </div>
        </Field>
      </Modal>
    </>
  );
}

/*
  Recording a filing.

  This used to be two text inputs and a button sitting inside every open row,
  which made each row four times the height of the one fact it carried and
  turned a calendar of deadlines into a column of forms. A table is for
  scanning. Filing is a deliberate act that happens a few times a year, and it
  belongs behind a button like every other deliberate act in the workspace.
*/
function RecordFiling({ item, onFiled }: Readonly<{ item: ComplianceItem; onFiled: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [evidence, setEvidence] = React.useState("");
  const [filing, setFiling] = React.useState("");

  const record = useAction(async () => {
    await api(`/compliance/${item.id}/complete`, {
      method: "POST",
      body: { evidence_reference: evidence.trim() || null, filing_number: filing.trim() || null },
    });
    setEvidence("");
    setFiling("");
    setOpen(false);
    onFiled();
  });

  const ready = !item.evidence_required || evidence.trim().length > 0;

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        Record filing
      </Button>
      <Modal
        open={open}
        title="Record a filing"
        subtitle={item.requirement}
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!ready || record.busy}
              onClick={() => void record.run()}
            >
              Record it
            </Button>
          </>
        }
      >
        {record.error ? (
          <Refusal
            title="That filing was not recorded"
            reason={record.error.message}
            reasons={record.error.reasons}
          />
        ) : null}

        <Field
          label={item.evidence_required ? "Evidence" : "Evidence, optional"}
          required={item.evidence_required}
          hint="The acknowledgement, receipt or portal link. Done without it cannot be shown to anybody."
        >
          <Input
            value={evidence}
            onChange={(event) => setEvidence(event.target.value)}
            placeholder="Link or reference"
          />
        </Field>

        <Field label="Filing number" hint="If the regulator issued one.">
          <Input
            value={filing}
            onChange={(event) => setFiling(event.target.value)}
            placeholder="Optional"
          />
        </Field>

        {item.recurrence in ROLLS_FORWARD ? (
          <Notice tone="info" title="This one comes back">
            {`Recording the filing moves it on to the next ${ROLLS_FORWARD[item.recurrence]} and reopens it. It does not leave the calendar.`}
          </Notice>
        ) : null}
      </Modal>
    </>
  );
}

/*
  A tab set with no "all" in it is four filters and no list. Whoever opens this
  page wants to see the calendar first and then narrow it, and a default of
  "Due" quietly hides everything that has been filed, which is most of the
  record after the first year.
*/
const EMPTY_BY_TAB: Record<string, string> = {
  all: "Nothing is on the calendar for this entity",
  due_soon: "Nothing is due soon",
  overdue: "Nothing is overdue",
  completed: "Nothing has been filed yet",
  superseded: "No item has been superseded",
};

export default function Compliance() {
  const { entity } = useSession();
  const { has } = useRoles();
  const canFile = has("counsel", "head_of_legal", "admin");
  const [tab, setTab] = React.useState("all");

  const all = useApi<ComplianceItem[]>("/compliance", [entity]);

  const items = all.data ?? [];
  const rows = React.useMemo(() => {
    if (tab === "due_soon") return items.filter(isDueSoon);
    if (tab === "overdue") return items.filter(isOverdue);
    if (tab === "completed") return items.filter((item) => item.status === "completed");
    if (tab === "superseded") return items.filter((item) => item.status === "superseded");
    return items;
  }, [items, tab]);

  const evidenceGaps = items.filter(
    (item) =>
      item.status === "completed" && item.evidence_required && item.evidence_reference === null,
  ).length;

  const unowned = items.filter(
    (item) => item.status === "open" && item.accountable_owner_name === null,
  ).length;

  const counts = {
    all: items.length,
    due_soon: items.filter(isDueSoon).length,
    overdue: items.filter(isOverdue).length,
    completed: items.filter((item) => item.status === "completed").length,
    superseded: items.filter((item) => item.status === "superseded").length,
  };

  return (
    <div className="space-y-6">
      <PageTitle
        title="Compliance calendar"
        subtitle={
          "What the organisation itself owes a regulator, as opposed to what a contract owes a " +
          "counterparty. Each filing has an accountable owner, the evidence it needs, and the " +
          "version of the rule that applied at the time."
        }
        actions={canFile ? <AddRequirement onAdded={all.reload} /> : undefined}
      />

      {evidenceGaps > 0 ? (
        <Notice
          tone="warn"
          title={`${evidenceGaps} completed ${plural(evidenceGaps, "filing", "filings")} ${evidenceGaps === 1 ? "has" : "have"} no evidence`}
        >
          A filing recorded as done without its evidence cannot be shown to a board or a funder.
        </Notice>
      ) : null}

      {unowned > 0 ? (
        <Notice
          tone="warn"
          title={`${unowned} ${plural(unowned, "item has", "items have")} no owner`}
        >
          A deadline recorded against nobody passes with everybody assuming it was somebody else's.
        </Notice>
      ) : null}

      <Tabs
        tabs={[
          { id: "all", label: "All", badge: counts.all },
          { id: "due_soon", label: "Due soon", badge: counts.due_soon },
          { id: "overdue", label: "Overdue", badge: counts.overdue },
          { id: "completed", label: "Completed", badge: counts.completed },
          { id: "superseded", label: "Superseded", badge: counts.superseded },
        ]}
        active={tab}
        onChange={setTab}
      />

      <Card>
        <CardHeader
          title={`${rows.length} ${plural(rows.length, "item", "items")}`}
          subtitle={`Entity ${entity}`}
        />
        <div className="table-scroll">
          <div className="min-w-[60rem]">
            <Row cols={COLS} head>
              <div>Item</div>
              <div>Recurrence</div>
              <div>Next due</div>
              <div>Owner</div>
              <div>Evidence</div>
              <div className="text-right">Actions</div>
            </Row>

            <DataState
              loading={all.loading}
              errorMessage={all.error?.message}
              errorTitle="The calendar is not available to you"
              isEmpty={rows.length === 0}
              emptyTitle={EMPTY_BY_TAB[tab]}
            >
              {rows.map((item) => (
                <Row key={item.id} cols={COLS}>
                  <div className="min-w-0">
                    <div className="line-clamp-2 font-medium leading-snug" title={item.requirement}>
                      {item.requirement}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                      {item.statutory_reference ? <Mono>{item.statutory_reference}</Mono> : null}
                      <span>{item.jurisdiction}</span>
                      <span>{`v${item.version}`}</span>
                    </div>
                  </div>

                  <div className="text-sm">{titleCase(item.recurrence)}</div>

                  <DueCell item={item} />

                  <div className="min-w-0 truncate text-sm">
                    {item.accountable_owner_name ?? (
                      <span className="text-warning">Nobody</span>
                    )}
                  </div>

                  <EvidenceCell item={item} />

                  <div className="flex items-center justify-end gap-2">
                    {item.status === "open" && canFile ? (
                      <RecordFiling item={item} onFiled={all.reload} />
                    ) : null}
                    <RequirementVersion item={item} onDone={all.reload} />
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
