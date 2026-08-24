"use client";

import Link from "next/link";
import * as React from "react";

import { ConfirmDraft } from "@/components/app/confirm-draft";
import { Card, CardBody, Chips, Empty, Mono, PageTitle, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { RequestStatus } from "@/lib/types";
import { cn, formatDate, formatDateTime } from "@/lib/utils";

/*
  Sorting matters here more than on a list Legal reads, because a requester
  opens this page for one of two reasons: something is waiting on them, or they
  want to know where a particular request got to. Waiting on you first is the
  default for the first reason; the dates serve the second.
*/
const ORDERS = [
  { id: "waiting", label: "Waiting on me" },
  { id: "updated", label: "Last updated" },
  { id: "raised", label: "Recently raised" },
  { id: "expected", label: "Due soonest" },
] as const;

type Order = (typeof ORDERS)[number]["id"];

function sortRequests(rows: RequestStatus[], order: Order): RequestStatus[] {
  const when = (value: string | null) => (value ? new Date(value).getTime() : 0);

  return [...rows].sort((a, b) => {
    if (order === "waiting") {
      const mine = Number(Boolean(b.awaiting_confirmation)) - Number(Boolean(a.awaiting_confirmation));
      if (mine !== 0) return mine;
      return when(b.last_update) - when(a.last_update);
    }
    if (order === "expected") {
      // A request with no date is not the most urgent thing on the page, so it
      // sorts last rather than first, which is where an empty value lands if
      // nobody thinks about it.
      const left = a.expected_date ? when(a.expected_date) : Number.POSITIVE_INFINITY;
      const right = b.expected_date ? when(b.expected_date) : Number.POSITIVE_INFINITY;
      return left - right;
    }
    if (order === "raised") {
      return when(b.timeline[0]?.occurred_at ?? null) - when(a.timeline[0]?.occurred_at ?? null);
    }
    return when(b.last_update) - when(a.last_update);
  });
}

export default function MyRequests() {
  const { data, loading, error } = useApi<RequestStatus[]>("/requests/mine");
  const [order, setOrder] = React.useState<Order>("waiting");

  const rows = React.useMemo(() => sortRequests(data ?? [], order), [data, order]);
  const waiting = (data ?? []).filter((request) => request.awaiting_confirmation).length;

  return (
    <div className="space-y-6">
      <PageTitle
        title="My requests"
        subtitle={
          waiting
            ? `${waiting} of these is waiting on you. Everything else is with Legal.`
            : "Status is updated by lifecycle events, not by anyone typing it in."
        }
        actions={
          (data ?? []).length > 1 ? (
            <Chips options={[...ORDERS]} active={order} onChange={(id) => setOrder(id as Order)} label="Order" />
          ) : null
        }
      />

      {loading ? (
        <Spinner />
      ) : error ? (
        <Empty title="Your requests could not be loaded" detail={error.message} />
      ) : !data?.length ? (
        <Empty
          title="You have not raised a request yet"
          detail="Choosing a request type takes two clicks."
        />
      ) : (
        <div className="space-y-4">
          {rows.map((request) => (
            <Card key={request.reference}>
              <CardBody className="space-y-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">{request.subject}</div>
                    <Mono>{request.reference}</Mono>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium">{request.stage_label}</div>
                    <div className="text-xs text-muted-foreground">
                      {request.owner_first_name
                        ? `With ${request.owner_first_name}`
                        : "Not yet assigned"}
                      , updated {formatDateTime(request.last_update)}
                    </div>
                  </div>
                </div>

                <ol className="flex flex-wrap items-center gap-1.5">
                  {request.timeline.map((entry) => (
                    <li
                      key={entry.stage}
                      className={cn(
                        "rounded-md border px-2.5 py-1 text-xs",
                        entry.current
                          ? "border-brand bg-brand/10 font-medium text-brand"
                          : "text-muted-foreground",
                      )}
                    >
                      {entry.label}
                    </li>
                  ))}
                </ol>

                {request.expected_date ? (
                  <div className="text-xs text-muted-foreground">
                    Expected by {formatDate(request.expected_date)}
                  </div>
                ) : null}

                {/*
                  The one place a requester acts rather than watches. Everything
                  else on this page reports what Legal is doing; this is the
                  step that is theirs, and it is the reason the page is worth
                  opening.
                */}
                {request.awaiting_confirmation ? (
                  <ConfirmDraft
                    requestId={request.id}
                    waiting={request.awaiting_confirmation}
                  />
                ) : null}
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      <Link href="/portal" className="text-sm">
        Raise another request
      </Link>
    </div>
  );
}
