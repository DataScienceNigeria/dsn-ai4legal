"use client";

import Link from "next/link";

import { useSession } from "@/components/app/session";
import { Card, CardBody, CardHeader, Empty, Kpi, PageTitle, Pill, Row, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { OperationalReport, WeeklyUpdate } from "@/lib/types";
import { relativeHours, titleCase } from "@/lib/utils";

export default function DeliveryDashboard() {
  const { entity } = useSession();
  const report = useApi<OperationalReport>("/reports/operational", [entity]);
  const weekly = useApi<WeeklyUpdate>("/reports/weekly-update", [entity]);

  if (report.loading) return <Spinner label="Computing from lifecycle events" />;
  if (report.error) {
    return <Empty title="This report is not available to you" detail={report.error.message} />;
  }

  const data = report.data!;
  const maxAgeing = Math.max(1, ...data.ageing.map((bucket) => bucket.count));

  return (
    <div className="space-y-6">
      <PageTitle
        title="Legal delivery"
        subtitle={
          "Every figure here is computed from recorded lifecycle transitions, not from " +
          "manually entered dates, so a number on this page can always be traced to an event."
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
        <Kpi label="Open matters" value={data.open_matters} detail={`Across ${data.by_owner.length} owners`} />
        <Kpi
          label="Past service target"
          value={data.sla_breaches}
          tone={data.sla_breaches ? "bad" : "good"}
          detail={`${data.near_breaches} approaching`}
        />
        <Kpi label="Blocked" value={data.blocked} tone={data.blocked ? "warn" : "neutral"} detail="Awaiting someone" />
        <Kpi
          label="Median turnaround"
          value={data.turnaround_median_hours === null ? "Not yet" : relativeHours(data.turnaround_median_hours)}
          detail="Acceptance to execution"
        />
        <Kpi
          label="Overdue obligations"
          value={data.obligations_overdue}
          tone={data.obligations_overdue ? "bad" : "good"}
          detail={`${data.reviews_overdue} library reviews overdue`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Workload by owner" subtitle="Open matters, and how many are past target" />
          <div>
            <Row cols="minmax(0,1fr) 5.625rem 5.625rem" head>
              <div>Owner</div>
              <div className="text-right">Open</div>
              <div className="text-right">Past target</div>
            </Row>
            {data.by_owner.length === 0 ? (
              <Empty title="No open matters in this entity" />
            ) : (
              data.by_owner.map((owner) => (
                <Row key={owner.owner_name} cols="minmax(0,1fr) 5.625rem 5.625rem">
                  <div className="truncate">{owner.owner_name}</div>
                  <div className="text-right tabular-nums">{owner.open_matters}</div>
                  <div className="text-right">
                    {owner.breached ? (
                      <Pill tone="bad">{owner.breached}</Pill>
                    ) : (
                      <span className="text-muted-foreground">0</span>
                    )}
                  </div>
                </Row>
              ))
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Ageing" subtitle="Days since the matter was accepted" />
          <CardBody className="space-y-2.5">
            {data.ageing.map((bucket) => (
              <div key={bucket.label} className="flex items-center gap-3">
                <div className="w-20 shrink-0 text-xs text-muted-foreground">{bucket.label}</div>
                <div className="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
                  <div
                    className="h-full rounded-sm bg-secondary"
                    style={{ width: `${(bucket.count / maxAgeing) * 100}%` }}
                  />
                </div>
                <div className="w-8 text-right text-xs tabular-nums">{bucket.count}</div>
              </div>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="By tier" subtitle="Tier is derived by rule, never chosen by the requester" />
          <div>
            {Object.entries(data.by_tier).length === 0 ? (
              <Empty title="Nothing open" />
            ) : (
              Object.entries(data.by_tier)
                .sort(([left], [right]) => left.localeCompare(right))
                .map(([tier, count]) => (
                  <Row key={tier} cols="minmax(0,1fr) 3.75rem">
                    <div>{titleCase(tier)}</div>
                    <div className="text-right tabular-nums">{count}</div>
                  </Row>
                ))
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Weekly update"
            subtitle="Generated, not written. The Head of Legal approves before circulation."
            actions={<Link href="/workspace/capabilities" className="text-xs">AI usage</Link>}
          />
          <CardBody className="space-y-3 text-sm">
            {weekly.loading ? (
              <Spinner />
            ) : weekly.error ? (
              <div className="text-xs text-muted-foreground">{weekly.error.message}</div>
            ) : weekly.data ? (
              <>
                {(
                  [
                    ["Delivery", weekly.data.delivery],
                    ["Blockers", weekly.data.blockers],
                    ["Next actions", weekly.data.next_actions],
                  ] as const
                ).map(([heading, lines]) => (
                  <div key={heading}>
                    <div className="text-xs font-semibold text-muted-foreground">{heading}</div>
                    <ul className="mt-1 space-y-1">
                      {lines.map((line) => (
                        <li key={line} className="flex gap-2 leading-relaxed">
                          <span aria-hidden className="text-muted-foreground">&bull;</span>
                          <span>{line}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </>
            ) : null}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
