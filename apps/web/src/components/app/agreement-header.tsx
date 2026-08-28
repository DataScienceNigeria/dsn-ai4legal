"use client";

import Link from "next/link";
import * as React from "react";

import { Button, Mono, PageTitle, Pill } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { Contract, Vocabulary } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const STATUS_TONE: Record<string, "good" | "warn" | "neutral"> = {
  active: "good",
  executed: "good",
  in_closure: "warn",
  closed: "neutral",
  terminated: "neutral",
  lapsed: "neutral",
  superseded: "neutral",
};

/*
  The same heading on every page about one agreement.

  Each of these pages is reached from a row in the register and holds one aspect
  of it, so each has to say which agreement it is about and offer the way back.
  Written once because five pages restating it is five places to forget the
  counterparty's name.
*/
export function AgreementHeader({
  contractId,
  title,
  subtitle,
  actions,
}: Readonly<{
  contractId: string;
  title: string;
  subtitle: string;
  actions?: React.ReactNode;
}>) {
  const contract = useApi<Contract>(`/contracts/${contractId}`, [contractId]);
  const vocabulary = useApi<Vocabulary>("/lifecycle/vocabulary");
  const record = contract.data;

  const typeLabel =
    vocabulary.data?.agreement_types.find((term) => term.key === record?.agreement_type)?.label ??
    record?.agreement_type;

  return (
    <>
      <PageTitle
        title={title}
        subtitle={subtitle}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {actions}
            <Link href="/workspace/agreements" className="no-underline">
              <Button size="sm">All agreements</Button>
            </Link>
          </div>
        }
      />
      {record ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <Mono>{record.reference}</Mono>
          <span className="text-foreground">
            {record.counterparty?.legal_name ?? "No counterparty linked"}
          </span>
          <span>{typeLabel}</span>
          <Pill tone={STATUS_TONE[record.status] ?? "neutral"}>
            {vocabulary.data?.contract_statuses.find((term) => term.key === record.status)?.label ??
              record.status}
          </Pill>
          {record.end_date ? <span>{`Ends ${formatDate(record.end_date)}`}</span> : null}
        </div>
      ) : null}
    </>
  );
}
