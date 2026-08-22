"use client";

import Link from "next/link";

import { Card, CardBody, Empty, Mono, PageTitle, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { RequestStatus } from "@/lib/types";
import { cn, formatDate, formatDateTime } from "@/lib/utils";

export default function MyRequests() {
  const { data, loading, error } = useApi<RequestStatus[]>("/requests/mine");

  return (
    <div className="space-y-6">
      <PageTitle
        title="My requests"
        subtitle="Status is updated by lifecycle events, not by anyone typing it in."
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
          {data.map((request) => (
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
                          ? "border-primary bg-primary/10 font-medium text-primary"
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
