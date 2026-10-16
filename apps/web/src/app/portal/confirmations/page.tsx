"use client";

import Link from "next/link";

import { Button, Card, CardBody, Empty, Mono, PageTitle, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { AwaitingDecision } from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/utils";

/*
  Finance and Procurement confirm one aspect of a draft: the money, or the
  process. They have no workspace, so the step reached them only as a
  notification pointing at a page that turned them away. This is where it is.
*/
export default function Confirmations() {
  const waiting = useApi<AwaitingDecision[]>("/approvals/awaiting");
  const rows = waiting.data ?? [];

  return (
    <div className="space-y-6">
      <PageTitle
        title="Confirmations"
        subtitle="Drafts waiting on your confirmation. Legal checks the wording; you confirm the part that is yours."
      />

      {waiting.loading ? (
        <Spinner />
      ) : waiting.error ? (
        <Empty title="Your confirmations could not be loaded" detail={waiting.error.message} />
      ) : rows.length === 0 ? (
        <Empty
          title="Nothing is waiting on you"
          detail="When a draft reaches your step, it appears here and you are notified."
        />
      ) : (
        <div className="space-y-3">
          {rows.map((row) => (
            <Card key={row.approval_id}>
              <CardBody className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <div className="text-base font-semibold">{row.matter_title}</div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                    <Mono>{row.matter_number}</Mono>
                    <span>{row.step_name}</span>
                    {row.counterparty ? <span>With {row.counterparty}</span> : null}
                    {row.value_amount !== null ? (
                      <span>{formatMoney(row.value_amount, row.value_currency ?? "NGN")}</span>
                    ) : null}
                    {row.due_at ? <span>Due {formatDate(row.due_at)}</span> : null}
                  </div>
                  {row.changes_requested ? (
                    <p className="text-sm italic text-muted-foreground">
                      You asked for a change: {row.changes_requested}
                    </p>
                  ) : null}
                </div>
                <Link href={`/portal/confirmations/${row.approval_id}`} className="no-underline">
                  <Button size="sm" variant="primary">
                    Read the draft
                  </Button>
                </Link>
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
