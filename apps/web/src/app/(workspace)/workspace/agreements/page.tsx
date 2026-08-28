"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

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
} from "@/components/ui";
import { api, query as queryString } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Contract, Obligation } from "@/lib/types";
import { formatDate, titleCase } from "@/lib/utils";

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
            <Link href={`/workspace/archive/${contract.id}/obligations`} className="no-underline">
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

const COLS = "10.625rem minmax(0,1fr) 9.375rem 10.625rem 7.5rem 9.375rem 6.25rem";

export default function Archive() {
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
        title="Executed archive"
        subtitle={
          "The authoritative record. Each executed copy is immutable for its retention period, " +
          "and a later upload is a linked amendment rather than a replacement."
        }
        actions={
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search counterparty, reference or clause text"
            className="w-full sm:w-72 lg:w-80"
          />
        }
      />

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
              <div>Contract</div>
              <div>Counterparty</div>
              <div>Type</div>
              <div>Matter</div>
              <div>Executed</div>
              <div>Record</div>
              <div>Agreement</div>
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
              data.map((contract) => (
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
                  {/*
                    The concluded matter, reached by its number.

                    This is the only route to a matter that has been executed:
                    the working list holds work in hand. It is a column of its
                    own rather than a link hidden on the counterparty name,
                    which used to read as "leave this page" on the very row the
                    reader had just come to open.
                  */}
                  <Link
                    href={`/workspace/matters/${contract.matter_id}`}
                    className="min-w-0 truncate text-xs no-underline hover:underline"
                  >
                    {contract.matter_number ?? "Linked matter"}
                  </Link>
                  <div className="text-xs">{formatDate(contract.executed_at)}</div>
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
                  <div>
                    <More label="Action">
                      <MenuItem href={`/workspace/archive/${contract.id}/obligations`}>
                        View obligations
                      </MenuItem>
                      {canAct ? (
                        <MenuItem onClick={() => setRenewing(contract)}>Renew agreement</MenuItem>
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

      <Notice title="What the archive holds">
        For each agreement: the executed copy, every approval that bound to its hash, the
        signature certificate and the full metadata. <strong>Signed original</strong> marks the
        file the parties actually signed, set once at execution; a later upload is a linked
        amendment rather than a replacement, so exactly one record per agreement carries it. The
        content hash is what ties the file to the approvals that authorised it.
      </Notice>
    </div>
  );
}
