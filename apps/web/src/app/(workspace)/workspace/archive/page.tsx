"use client";

import Link from "next/link";
import * as React from "react";

import { useRoles, useSession } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  DataState,
  Empty,
  Input,
  Modal,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Row,
  Spinner,
} from "@/components/ui";
import { api, query as queryString } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Contract } from "@/lib/types";
import { formatDate, formatMoney, titleCase } from "@/lib/utils";

/*
  Everything that can be done to an executed agreement lives here: open the
  renewal window as a task, pull the obligations out of the text, and read the
  provenance that ties the record back to the versions it was built from.
*/
function ContractActions({
  contract,
  onClose,
}: Readonly<{ contract: Contract; onClose: () => void }>) {
  const { has } = useRoles();
  const provenance = useApi<Record<string, unknown>>(`/contracts/${contract.id}/provenance`, [
    contract.id,
  ]);
  const obligations = useApi<{ id: string; reference: string; name: string; status: string }[]>(
    `/contracts/${contract.id}/obligations`,
    [contract.id],
  );
  const [leadTime, setLeadTime] = React.useState("60");
  const [note, setNote] = React.useState<string | null>(null);

  const renewalTask = useAction(async () => {
    await api(`/contracts/${contract.id}/renewal-task${queryString({ lead_time_days: leadTime })}`, {
      method: "POST",
    });
    setNote("A renewal task is open and falls due before the notice deadline.");
    obligations.reload();
  });

  const extract = useAction(async () => {
    await api(`/ai/extract-obligations/${contract.id}`, { method: "POST" });
    setNote("Obligations were proposed. Each stays a proposal until Legal confirms it.");
    obligations.reload();
  });

  const canAct = has("legal_ops", "counsel", "head_of_legal", "admin");

  return (
    <Modal
      open
      title={contract.reference}
      subtitle={`${titleCase(contract.agreement_type)} with ${contract.counterparty?.legal_name ?? "an unlinked counterparty"}`}
      width="lg"
      onClose={onClose}
    >
      {note ? <Notice tone="good" title="Done">{note}</Notice> : null}
      {renewalTask.error ? (
        <Refusal
          title="No renewal task was opened"
          reason={renewalTask.error.message}
          reasons={Object.values(renewalTask.error.fieldErrors)}
        />
      ) : null}
      {extract.error ? (
        <Refusal title="Extraction was refused" reason={extract.error.message} reasons={extract.error.reasons} />
      ) : null}

      {canAct ? (
        <Card>
          <CardHeader
            title="Actions"
            subtitle="A renewal window closes whether or not anyone is watching it."
          />
          <CardBody className="flex flex-wrap items-end gap-3">
            <div className="w-32">
              <span className="mb-1.5 block text-sm font-medium">Lead time, days</span>
              <Input
                type="number"
                value={leadTime}
                onChange={(event) => setLeadTime(event.target.value)}
              />
            </div>
            <Button variant="primary" disabled={renewalTask.busy} onClick={() => void renewalTask.run()}>
              Open a renewal task
            </Button>
            <Button disabled={extract.busy} onClick={() => void extract.run()}>
              Extract the obligations
            </Button>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader title="Obligations on this agreement" />
        <CardBody>
          <DataState
            loading={obligations.loading}
            errorMessage={obligations.error?.message}
            isEmpty={(obligations.data ?? []).length === 0}
            emptyTitle="Nothing has been extracted from this agreement yet"
          >
            <ul className="space-y-1.5 text-sm">
              {(obligations.data ?? []).map((obligation) => (
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

const COLS = "10.625rem minmax(0,1fr) 9.375rem 7.5rem 7.5rem 8.125rem 6.25rem";

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

      <Card>
        <CardHeader title={`${data?.length ?? 0} agreements`} subtitle={`Entity ${entity}`} />
        <div className="table-scroll">
          <div className="min-w-[70rem]">
            <Row cols={COLS} head>
              <div>Contract</div>
              <div>Counterparty</div>
              <div>Type</div>
              <div>Value</div>
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
                  <Mono>{contract.reference}</Mono>
                  <Link
                    href={`/workspace/matters/${contract.matter_id}`}
                    className="min-w-0 truncate text-foreground no-underline hover:underline"
                  >
                    {contract.counterparty?.legal_name ?? "Not linked"}
                  </Link>
                  <div className="text-xs">{titleCase(contract.agreement_type)}</div>
                  <div className="text-xs tabular-nums">
                    {formatMoney(contract.value_amount, contract.value_currency)}
                  </div>
                  <div className="text-xs">{formatDate(contract.executed_at)}</div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {contract.authoritative ? (
                      <Pill tone="good">
                        <span aria-hidden className="mr-1">&#128274;</span>Authoritative
                      </Pill>
                    ) : (
                      <Pill tone="neutral">Draft</Pill>
                    )}
                    {contract.executed_outside_platform ? <Pill tone="warn">Wet ink</Pill> : null}
                  </div>
                  <div>
                    <Button size="sm" onClick={() => setOpen(contract)}>
                      Open
                    </Button>
                  </div>
                </Row>
              ))
            )}
          </div>
        </div>
      </Card>

      {open ? <ContractActions contract={open} onClose={() => setOpen(null)} /> : null}

      <Notice title="What the archive holds">
        For each agreement: the executed copy, every approval that bound to its hash, the
        signature certificate and the full metadata. The content hash is what ties the file to the
        approvals that authorised it.
      </Notice>
    </div>
  );
}
