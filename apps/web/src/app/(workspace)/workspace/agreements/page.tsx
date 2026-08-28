"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Changes, Issues } from "@/components/app/lifecycle-queues";
import { useRoles, useSession } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  DataState,
  Empty,
  Field,
  Input,
  MenuItem,
  Modal,
  Mono,
  More,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Row,
  Spinner,
  Tabs,
} from "@/components/ui";
import { api, query as queryString } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Contract, Obligation } from "@/lib/types";
import { cn, formatDate, titleCase } from "@/lib/utils";

/*
  The agreement itself: what it is, what came out of it, and what it was built
  from.

  It used to open on a row of loose buttons. "Extract the obligations" and
  "Open a renewal task" sat side by side in an Actions card, which asked the
  reader to know the difference between two things they had never met before
  they could read the agreement at all. Both are now items on the row's Action
  menu, chosen before the panel opens, and what remains here is the record.
*/
function ContractPanel({
  contract,
  onClose,
}: Readonly<{ contract: Contract; onClose: () => void }>) {
  const provenance = useApi<Record<string, unknown>>(`/contracts/${contract.id}/provenance`, [
    contract.id,
  ]);
  const obligations = useApi<Obligation[]>(`/contracts/${contract.id}/obligations`, [contract.id]);
  const held = obligations.data ?? [];

  return (
    <Modal
      open
      title={contract.reference}
      subtitle={`${titleCase(contract.agreement_type)} with ${contract.counterparty?.legal_name ?? "an unlinked counterparty"}`}
      width="lg"
      onClose={onClose}
    >
      <p className="text-xs text-muted-foreground">
        Executed {formatDate(contract.executed_at)} under matter{" "}
        <Link href={`/workspace/matters/${contract.matter_id}`}>
          {contract.matter_number ?? "linked"}
        </Link>
      </p>

      <Card>
        <CardHeader
          title="Obligations on this agreement"
          subtitle="What this contract requires of us, and by when."
          actions={
            <Link href={`/workspace/agreements/${contract.id}/obligations`} className="no-underline">
              <Button size="sm">{held.length ? "View them" : "Extract them"}</Button>
            </Link>
          }
        />
        <CardBody>
          <DataState
            loading={obligations.loading}
            errorMessage={obligations.error?.message}
            isEmpty={held.length === 0}
            emptyTitle="Nothing has been extracted from this agreement yet"
          >
            <ul className="space-y-1.5 text-sm">
              {held.map((obligation) => (
                <li key={obligation.id} className="flex items-center gap-2">
                  <Pill tone={obligation.status === "open" ? "good" : "warn"}>
                    {titleCase(obligation.status)}
                  </Pill>
                  <Mono>{obligation.reference}</Mono>
                  <span className="min-w-0 truncate">{obligation.name}</span>
                </li>
              ))}
            </ul>
          </DataState>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Provenance"
          subtitle="Which template version, which clause versions, and which hash was signed."
        />
        <CardBody>
          <DataState
            loading={provenance.loading}
            errorMessage={provenance.error?.message}
            isEmpty={!provenance.data}
            emptyTitle="No provenance is recorded"
          >
            <pre className="overflow-x-auto rounded-md border bg-muted/30 p-3 text-xs leading-relaxed">
              {JSON.stringify(provenance.data, null, 2)}
            </pre>
          </DataState>
        </CardBody>
      </Card>
    </Modal>
  );
}

/*
  Opening a renewal window, asked for once rather than offered as a permanent
  button beside an unrelated one.
*/
function RenewalDialog({
  contract,
  onDone,
  onClose,
}: Readonly<{ contract: Contract; onDone: (message: string) => void; onClose: () => void }>) {
  const [leadTime, setLeadTime] = React.useState("60");

  const open = useAction(async () => {
    await api(`/contracts/${contract.id}/renewal-task${queryString({ lead_time_days: leadTime })}`, {
      method: "POST",
    });
    onDone("A renewal task is open and falls due before the notice deadline.");
    onClose();
  });

  return (
    <Modal
      open
      title="Open a renewal task"
      subtitle="A renewal window closes whether or not anyone is watching it. The task falls due at the notice deadline, less the lead time."
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={open.busy} onClick={() => void open.run()}>
            Open the task
          </Button>
        </>
      }
    >
      {open.error ? (
        <Refusal title="No renewal task was opened" reason={open.error.message} />
      ) : null}
      <Field label="Lead time, days" hint="How long before the deadline the task should fall due.">
        <Input type="number" value={leadTime} onChange={(event) => setLeadTime(event.target.value)} />
      </Field>
    </Modal>
  );
}

const COLS = "10.625rem minmax(0,1fr) 9.375rem 8rem 8rem 9.375rem 5.5rem";

/*
  Sorting the register.

  A register that can only be read in the order it was written is one nobody can
  ask "what ends soonest" or "what is the largest thing we signed", which are
  the two questions a legal team actually brings to it. Sorting is in the
  client because the whole entity's agreements are already in hand; a register
  of this size does not need a round trip to reorder.
*/
type Sortable = "reference" | "counterparty" | "agreement_type" | "executed_at" | "end_date";

const SORT_LABEL: Record<Sortable, string> = {
  reference: "Reference",
  counterparty: "Counterparty",
  agreement_type: "Type",
  executed_at: "Executed",
  end_date: "Ends",
};

function sortValue(contract: Contract, key: Sortable): string | number {
  if (key === "counterparty") return (contract.counterparty?.legal_name ?? "").toLowerCase();
  if (key === "agreement_type") return contract.agreement_type.toLowerCase();
  if (key === "executed_at") return contract.executed_at ?? "";
  if (key === "end_date") return contract.end_date ?? "";
  return contract.reference.toLowerCase();
}

/*
  A column heading that sorts, and says which way.

  The arrow is on the active column only. A row of arrows tells the reader every
  column is sorted, which is the one thing that cannot be true.
*/
function SortHead({
  column,
  active,
  descending,
  onSort,
  className,
}: Readonly<{
  column: Sortable;
  active: boolean;
  descending: boolean;
  onSort: (column: Sortable) => void;
  className?: string;
}>) {
  return (
    <button
      type="button"
      onClick={() => onSort(column)}
      className={cn(
        "flex items-center gap-1 text-left uppercase tracking-wide transition-colors hover:text-foreground",
        active && "text-foreground",
        className,
      )}
      aria-sort={active ? (descending ? "descending" : "ascending") : "none"}
    >
      {SORT_LABEL[column]}
      <span aria-hidden className={cn("text-[0.65rem]", !active && "opacity-0")}>
        {descending ? "\u25be" : "\u25b4"}
      </span>
    </button>
  );
}

/*
  Signed paper, and everything that happens to it afterwards.

  This was two destinations, Archive and After signature, and the split did not
  survive contact with the register. "Archive" says dead storage, and these rows
  are agreements being performed, varied and closed. "After signature" held the
  queue of what has gone wrong across them, which is the same subject read the
  other way round.

  The queue survives the merge as a tab rather than folding into the row menu,
  and that is deliberate. Row actions answer "what about this one"; the queue
  answers "what is open across the whole portfolio and who owns it", which no
  arrangement of row actions can answer without opening every row.
*/
const TABS = [
  {
    id: "register",
    label: "All agreements",
    roles: ["counsel", "head_of_legal", "admin", "auditor", "management"],
  },
  /*
    The queues are legal's working records and the auditor's evidence.

    Management reads the register and the exposure report, which answer what the
    organisation signed and what it conceded. An issue queue with assignees and
    a triage button is how the department runs itself, and a board watching a
    work queue is a board doing somebody else's job.
  */
  { id: "issues", label: "Issues", roles: ["counsel", "head_of_legal", "admin", "auditor"] },
  { id: "changes", label: "Changes", roles: ["counsel", "head_of_legal", "admin", "auditor"] },
];

export default function Agreements() {
  const [tab, setTab] = React.useState("register");
  const { entity } = useSession();
  const [query, setQuery] = React.useState("");
  const [debounced, setDebounced] = React.useState("");

  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 250);
    return () => clearTimeout(timer);
  }, [query]);

  const path = debounced ? `/contracts?q=${encodeURIComponent(debounced)}` : "/contracts";
  const { data, loading, error } = useApi<Contract[]>(path, [entity, debounced]);
  const [open, setOpen] = React.useState<Contract | null>(null);
  const [renewing, setRenewing] = React.useState<Contract | null>(null);
  const [note, setNote] = React.useState<string | null>(null);
  const { has } = useRoles();
  const canAct = has("counsel", "head_of_legal", "admin");
  const router = useRouter();

  // Newest first, because the question a register is usually opened with is
  // "what did we just sign".
  // A tab a role cannot open is not offered. The API refuses independently.
  const tabs = TABS.filter((one) => has(...one.roles));
  const active = tabs.some((one) => one.id === tab) ? tab : (tabs[0]?.id ?? "register");

  const [sort, setSort] = React.useState<Sortable>("executed_at");
  const [descending, setDescending] = React.useState(true);

  function onSort(column: Sortable) {
    if (column === sort) {
      setDescending((previous) => !previous);
      return;
    }
    setSort(column);
    // Dates read newest first and names read A to Z. Carrying the previous
    // direction across means the first click on a name column shows Z.
    setDescending(column === "executed_at" || column === "end_date");
  }

  const rows = React.useMemo(() => {
    const all = [...(data ?? [])];
    all.sort((left, right) => {
      const a = sortValue(left, sort);
      const b = sortValue(right, sort);
      // Blanks last whichever way the column is pointing. A row with no end
      // date is not the earliest-ending agreement.
      if (a === "" && b !== "") return 1;
      if (b === "" && a !== "") return -1;
      if (a === b) return left.reference.localeCompare(right.reference);
      return (a < b ? -1 : 1) * (descending ? -1 : 1);
    });
    return all;
  }, [data, sort, descending]);


  /*
    A matter that has reached Live links straight to its own agreement. It used
    to link to this list, so the button read "Extract the obligations" and did
    nothing but change the page, leaving the reader to work out which row was
    theirs and that the action was another click inside it.

    Read from the address rather than useSearchParams, which would need a
    Suspense boundary around a page that otherwise needs none.
  */
  const wanted = React.useMemo(() => {
    if (typeof globalThis.location === "undefined") return null;
    return new URLSearchParams(globalThis.location.search).get("contract");
  }, []);

  React.useEffect(() => {
    if (!wanted || open) return;
    const match = (data ?? []).find((contract) => contract.id === wanted);
    if (match) setOpen(match);
  }, [wanted, data, open]);

  return (
    <div className="space-y-6">
      <PageTitle
        title="Agreements"
        subtitle={
          "Everything signed, and everything that has happened to it since. Each executed copy " +
          "is immutable for its retention period, and a later upload is a linked amendment " +
          "rather than a replacement."
        }
        actions={
          active === "register" ? (
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search counterparty, reference or clause text"
              className="w-full sm:w-72 lg:w-80"
            />
          ) : undefined
        }
      />

      {tabs.length > 1 ? (
        <Tabs
          tabs={tabs.map(({ id, label }) => ({ id, label }))}
          active={active}
          onChange={setTab}
        />
      ) : null}

      {active === "issues" ? <Issues entity={entity} /> : null}
      {active === "changes" ? <Changes entity={entity} /> : null}

      {active !== "register" ? null : (
      <>
      {note ? (
        <Notice tone="good" title="Done">
          {note}
        </Notice>
      ) : null}

      <Card>
        <CardHeader title={`${data?.length ?? 0} agreements`} subtitle={`Entity ${entity}`} />
        <div className="table-scroll">
          <div className="min-w-[70rem]">
            <Row cols={COLS} head>
              <SortHead column="reference" active={sort === "reference"} descending={descending} onSort={onSort} />
              <SortHead column="counterparty" active={sort === "counterparty"} descending={descending} onSort={onSort} />
              <SortHead column="agreement_type" active={sort === "agreement_type"} descending={descending} onSort={onSort} />
              <SortHead column="executed_at" active={sort === "executed_at"} descending={descending} onSort={onSort} />
              <SortHead column="end_date" active={sort === "end_date"} descending={descending} onSort={onSort} />
              <div>Record</div>
              <div className="text-right">Action</div>
            </Row>

            {loading ? (
              <Spinner />
            ) : error ? (
              <Empty title="The archive is not available to you" detail={error.message} />
            ) : !data?.length ? (
              <Empty
                title="No executed agreement matches"
                detail="A restricted agreement is absent from this list rather than redacted in it."
              />
            ) : (
              rows.map((contract) => (
                <Row key={contract.id} cols={COLS}>
                  {/*
                    The reference opens the record: the signed copy, its
                    provenance and the duties on it. Reading the agreement is
                    not a task, so it is the row's own click rather than an
                    item on the menu, which carries the two things a person
                    does to an executed agreement and nothing else.
                  */}
                  <button
                    type="button"
                    onClick={() => setOpen(contract)}
                    className="min-w-0 text-left"
                  >
                    <Mono>{contract.reference}</Mono>
                    {/*
                      The matter that produced it, as provenance rather than as
                      a destination. It used to be a column of its own, which
                      spent nine rem of a register saying where each row came
                      from; the agreement's own record links to it.
                    */}
                    {contract.matter_number ? (
                      <div className="truncate text-xs text-muted-foreground">
                        {contract.matter_number}
                      </div>
                    ) : null}
                  </button>
                  {/*
                    Plain text, not a link back to the matter. The matter's own
                    last step sends the reader here, so a link the other way
                    closed a loop between two screens and made the counterparty
                    name mean "leave this page". The matter is still reachable,
                    named inside the agreement where it belongs as provenance.
                  */}
                  <div className="min-w-0 truncate">
                    {contract.counterparty?.legal_name ?? "Not linked"}
                  </div>
                  <div className="text-xs">{titleCase(contract.agreement_type)}</div>
                  <div className="text-xs">{formatDate(contract.executed_at)}</div>
                  {/*
                    When it ends, and whether the last day to give notice has
                    gone. The register is read to answer "what is ending
                    soonest" more often than it is read to answer anything else,
                    and the notice date is the one that cannot be recovered
                    once it passes.
                  */}
                  <div className="min-w-0 text-xs">
                    {contract.end_date ? (
                      <>
                        {formatDate(contract.end_date)}
                        {contract.termination_deadline ? (
                          <div className="text-muted-foreground">
                            {`Notice by ${formatDate(contract.termination_deadline)}`}
                          </div>
                        ) : null}
                      </>
                    ) : (
                      <span className="text-muted-foreground">No end date</span>
                    )}
                  </div>
                  {/*
                    Whether this file is the agreement or a copy of one. Set at
                    execution and never afterwards: a later upload is a linked
                    amendment, so exactly one record per agreement carries it.
                  */}
                  <div className="flex flex-wrap items-center gap-1.5">
                    {contract.authoritative ? (
                      <Pill tone="good">
                        <span aria-hidden className="mr-1">&#128274;</span>Signed original
                      </Pill>
                    ) : (
                      <Pill tone="neutral">Not the original</Pill>
                    )}
                    {contract.executed_outside_platform ? <Pill tone="warn">Wet ink</Pill> : null}
                  </div>
                  {/*
                    Everything that happens to this agreement, each on its own
                    page. The queue across all of them is a tab above; this menu
                    is about the one row it sits on.
                  */}
                  <div className="flex justify-end">
                    <More label="Action">
                      <MenuItem href={`/workspace/agreements/${contract.id}/obligations`}>
                        View obligations
                      </MenuItem>
                      <MenuItem href={`/workspace/agreements/${contract.id}/issues`}>
                        {contract.open_issue_count
                          ? `Issues (${contract.open_issue_count} open)`
                          : "Issues"}
                      </MenuItem>
                      <MenuItem href={`/workspace/agreements/${contract.id}/changes`}>
                        {contract.open_change_count
                          ? `Changes (${contract.open_change_count} waiting)`
                          : "Changes"}
                      </MenuItem>
                      {canAct ? (
                        <MenuItem href={`/workspace/agreements/${contract.id}/register`}>
                          Register entry
                        </MenuItem>
                      ) : null}
                      {canAct ? (
                        <MenuItem onClick={() => setRenewing(contract)}>Renew agreement</MenuItem>
                      ) : null}
                      {canAct ? (
                        <MenuItem href={`/workspace/agreements/${contract.id}/closure`}>
                          Close the agreement
                        </MenuItem>
                      ) : null}
                    </More>
                  </div>
                </Row>
              ))
            )}
          </div>
        </div>
      </Card>

      {open ? <ContractPanel contract={open} onClose={() => setOpen(null)} /> : null}

      {renewing ? (
        <RenewalDialog
          contract={renewing}
          onDone={setNote}
          onClose={() => setRenewing(null)}
        />
      ) : null}

      <Notice title="What the register holds">
        For each agreement: the executed copy, every approval that bound to its hash, the
        signature certificate and the full metadata. <strong>Signed original</strong> marks the
        file the parties actually signed, set once at execution; a later upload is a linked
        amendment rather than a replacement, so exactly one record per agreement carries it. The
        content hash is what ties the file to the approvals that authorised it.
      </Notice>
      </>
      )}
    </div>
  );
}
