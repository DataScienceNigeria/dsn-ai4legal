"use client";

import Link from "next/link";

import { useSession } from "@/components/app/session";
import { TierPill } from "@/components/app/status";
import { Card, CardHeader, Empty, PageTitle, Pill, Row, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { TriageRow } from "@/lib/types";
import { formatDate, relativeHours } from "@/lib/utils";

export default function TriageQueue() {
  const { entity } = useSession();
  const { data, loading, error } = useApi<TriageRow[]>("/triage", [entity]);

  return (
    <div className="space-y-6">
      <PageTitle
        title="Triage queue"
        subtitle={
          "Sorted by declared deadline, then by age. A request stays a request until Legal " +
          "accepts it, and the matter number is issued at acceptance rather than at submission."
        }
      />

      <Card>
        <CardHeader
          title="Awaiting triage"
          subtitle={data ? `${data.length} in ${entity}` : undefined}
        />
        <div>
          <Row cols="7.5rem minmax(0,1.4fr) minmax(0,1fr) 5.625rem 5rem 5.625rem 6.875rem" head>
            <div>Reference</div>
            <div>Request</div>
            <div>Counterparty</div>
            <div>Privacy</div>
            <div>Age</div>
            <div>Suggested</div>
            <div>Needed by</div>
          </Row>

          {loading ? (
            <Spinner />
          ) : error ? (
            <Empty title="The queue is not available to you" detail={error.message} />
          ) : !data?.length ? (
            <Empty
              title="Nothing is waiting"
              detail="Every request in this entity has been accepted, returned or closed."
            />
          ) : (
            data.map((row) => (
              <Link
                key={row.request_id}
                href={`/workspace/triage/${row.request_id}`}
                className="block no-underline text-foreground hover:bg-muted/60"
              >
                <Row cols="7.5rem minmax(0,1.4fr) minmax(0,1fr) 5.625rem 5rem 5.625rem 6.875rem">
                  <div className="font-mono text-2xs text-muted-foreground">{row.reference}</div>
                  <div className="min-w-0">
                    <div className="truncate font-medium">{row.subject}</div>
                    <div className="truncate text-xs text-muted-foreground">{row.request_type}</div>
                  </div>
                  <div className="truncate">{row.counterparty ?? "Not stated"}</div>
                  <div>
                    {row.privacy_flag ? (
                      <Pill tone="warn">
                        <span aria-hidden className="mr-1">&#9873;</span>Flagged
                      </Pill>
                    ) : (
                      <span className="text-xs text-muted-foreground">None</span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground">{relativeHours(row.age_hours)}</div>
                  <div>
                    <TierPill tier={row.suggested_tier} />
                  </div>
                  <div className="text-xs text-muted-foreground">{formatDate(row.required_date)}</div>
                </Row>
              </Link>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
