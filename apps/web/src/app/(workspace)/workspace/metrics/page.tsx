"use client";

import * as React from "react";

import { useSession } from "@/components/app/session";
import {
  Card,
  CardBody,
  CardHeader,
  DataState,
  Empty,
  Kpi,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Row,
  Tabs,
} from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type {
  DeviationPattern,
  ExposureReport,
  InboxAccuracy,
  KpiRow,
  QualitySampleRow,
} from "@/lib/types";
import { formatDate, percent, titleCase } from "@/lib/utils";

const KPI_COLS = "minmax(0,1.6fr) 7.5rem 7.5rem 7.5rem 6.875rem";
const PATTERN_COLS = "7.5rem 10rem 6.25rem 6.25rem 6.25rem 6.875rem 7.5rem";
const ACCURACY_COLS = "minmax(0,1fr) 6.875rem 6.875rem 8.125rem 8.125rem 6.25rem";
const SAMPLE_COLS = "6.25rem minmax(0,1.6fr) 8.75rem 7.5rem";

function trackTone(onTrack: boolean | null) {
  if (onTrack === null) return "neutral" as const;
  return onTrack ? ("good" as const) : ("bad" as const);
}

function trackLabel(onTrack: boolean | null) {
  if (onTrack === null) return "No reading";
  return onTrack ? "On track" : "Behind";
}

function Measure({ row }: Readonly<{ row: KpiRow }>) {
  const suffix = row.unit === "percent" ? "%" : "";
  const shown = row.current === null ? "Not yet measured" : `${row.current}${suffix}`;

  return (
    <Row cols={KPI_COLS}>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{row.name}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">{row.measurement_method}</div>
        <Mono>{row.code}</Mono>
      </div>
      <div className="text-sm">{row.baseline ?? "Not set"}</div>
      <div className="text-sm font-medium">{shown}</div>
      <div className="text-sm">{row.phase_1_target ?? "Not set"}</div>
      <div>
        <Pill tone={trackTone(row.on_track)}>{trackLabel(row.on_track)}</Pill>
      </div>
    </Row>
  );
}

function Improvement({ entity }: Readonly<{ entity: string }>) {
  const kpis = useApi<KpiRow[]>("/reports/kpi", [entity]);
  const rows = kpis.data ?? [];

  return (
    <Card>
      <CardHeader
        title="Every KPI against baseline and target"
        subtitle="The measurement definition sits beside each figure, so the number can be argued with."
      />
      <div className="table-scroll">
        <div className="min-w-[51.25rem]">
          <Row cols={KPI_COLS} head>
            <div>Measure</div>
            <div>Baseline</div>
            <div>Current</div>
            <div>Phase 1 target</div>
            <div>Status</div>
          </Row>
          <DataState
            loading={kpis.loading}
            errorMessage={kpis.error?.message}
            errorTitle="KPIs are not available to you"
            isEmpty={rows.length === 0}
            emptyTitle="No baseline has been recorded"
          >
            {rows.map((row) => (
              <Measure key={row.code} row={row} />
            ))}
          </DataState>
        </div>
      </div>
    </Card>
  );
}

function ConcededClauses({ report }: Readonly<{ report: ExposureReport }>) {
  return (
    <Card>
      <CardHeader
        title="Clauses conceded most often"
        subtitle="Evidence for revising the playbook, rather than impression."
      />
      <div className="table-scroll">
        <div className="min-w-[35rem]">
          <Row cols="minmax(0,1fr) 7.5rem 11.25rem" head>
            <div>Clause</div>
            <div>Conceded</div>
            <div>Critical or material</div>
          </Row>
          <DataState
            loading={false}
            isEmpty={report.clauses_conceded.length === 0}
            emptyTitle="No concession has been recorded"
          >
            {report.clauses_conceded.map((row) => (
              <Row key={row.clause_category} cols="minmax(0,1fr) 7.5rem 11.25rem">
                <div className="text-sm">{row.clause_category}</div>
                <div className="text-sm">{row.conceded}</div>
                <div>
                  <Pill tone={row.critical_or_material > 0 ? "bad" : "neutral"}>
                    {row.critical_or_material}
                  </Pill>
                </div>
              </Row>
            ))}
          </DataState>
        </div>
      </div>
    </Card>
  );
}

function Exposure({ entity }: Readonly<{ entity: string }>) {
  const report = useApi<ExposureReport>("/reports/exposure", [entity]);
  const data = report.data;

  return (
    <DataState
      loading={report.loading}
      errorMessage={report.error?.message}
      errorTitle="Exposure reporting is not available to you"
      isEmpty={data === null}
      emptyTitle="Nothing to report"
    >
      {data ? (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Kpi label="Deviations accepted" value={data.deviations_accepted} />
            <Kpi
              label="Unusual liability positions"
              value={data.unusual_liability_positions.length}
              tone={data.unusual_liability_positions.length > 0 ? "warn" : "neutral"}
            />
            <Kpi
              label="Obligations at risk in 30 days"
              value={data.obligations_at_risk.length}
              tone={data.obligations_at_risk.length > 0 ? "warn" : "neutral"}
            />
          </div>

          <Notice tone="info" title="What this counts">
            {data.note}
          </Notice>

          <ConcededClauses report={data} />

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader title="Contracts on an unusual liability position" />
              <CardBody>
                {data.unusual_liability_positions.length === 0 ? (
                  <Empty title="Every executed agreement sits on a house or approved fallback position" />
                ) : (
                  <ul className="space-y-3">
                    {data.unusual_liability_positions.map((row) => (
                      <li key={row.reference} className="text-sm">
                        <Mono>{row.reference}</Mono>
                        <div className="mt-0.5">{row.reason}</div>
                        <div className="text-xs text-muted-foreground">
                          {titleCase(row.agreement_type)}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Obligations at risk" />
              <CardBody>
                {data.obligations_at_risk.length === 0 ? (
                  <Empty title="Nothing falls due in the next 30 days" />
                ) : (
                  <ul className="space-y-3">
                    {data.obligations_at_risk.map((row) => (
                      <li key={row.reference} className="text-sm">
                        <div className="flex items-center justify-between gap-3">
                          <span className="truncate">{row.name}</span>
                          <Pill tone={row.days_until_due < 0 ? "bad" : "warn"}>
                            {row.days_until_due < 0
                              ? `${Math.abs(row.days_until_due)} days overdue`
                              : `In ${row.days_until_due} days`}
                          </Pill>
                        </div>
                        <Mono>{row.reference}</Mono>
                      </li>
                    ))}
                  </ul>
                )}
              </CardBody>
            </Card>
          </div>
        </div>
      ) : null}
    </DataState>
  );
}

function ConcessionRate({ rate }: Readonly<{ rate: number | null }>) {
  if (rate === null) return <span className="text-xs text-muted-foreground">Undecided</span>;
  return <Pill tone={rate > 0.5 ? "warn" : "neutral"}>{percent(rate)}</Pill>;
}

function Patterns({ entity }: Readonly<{ entity: string }>) {
  const patterns = useApi<DeviationPattern[]>("/reports/deviation-patterns", [entity]);
  const rows = patterns.data ?? [];

  return (
    <Card>
      <CardHeader
        title="Which clauses are challenged, by whom, with what outcome"
        subtitle="A concession rate appears only once a finding has been decided."
      />
      <div className="table-scroll">
        <div className="min-w-[51.25rem]">
          <Row cols={PATTERN_COLS} head>
            <div>Clause</div>
            <div>Counterparty class</div>
            <div>Challenged</div>
            <div>Accepted</div>
            <div>Rejected</div>
            <div>Cleared by ops</div>
            <div>Concession rate</div>
          </Row>
          <DataState
            loading={patterns.loading}
            errorMessage={patterns.error?.message}
            errorTitle="Pattern reporting is not available to you"
            isEmpty={rows.length === 0}
            emptyTitle="No review finding has been recorded yet"
          >
            {rows.map((row) => (
              <Row key={`${row.clause_category}-${row.counterparty_class}`} cols={PATTERN_COLS}>
                <div className="text-sm">{row.clause_category}</div>
                <div className="text-sm">{titleCase(row.counterparty_class)}</div>
                <div className="text-sm">{row.challenged}</div>
                <div className="text-sm">{row.accepted}</div>
                <div className="text-sm">{row.rejected}</div>
                <div className="text-sm">{row.cleared_by_ops}</div>
                <div>
                  <ConcessionRate rate={row.concession_rate} />
                </div>
              </Row>
            ))}
          </DataState>
        </div>
      </div>
    </Card>
  );
}

function PrecisionCell({ value }: Readonly<{ value: number | null }>) {
  if (value === null) return <span className="text-xs text-muted-foreground">No reading</span>;
  return <Pill tone={value >= 0.85 ? "good" : "warn"}>{percent(value)}</Pill>;
}

function Accuracy({ entity }: Readonly<{ entity: string }>) {
  const accuracy = useApi<InboxAccuracy>("/reports/inbox-accuracy", [entity]);
  const sample = useApi<QualitySampleRow[]>("/quality-sample", [entity]);

  const data = accuracy.data;
  const categories = data?.categories ?? [];
  const samples = sample.data ?? [];
  const unreviewed = samples.filter((row) => !row.reviewed).length;
  const correction = data?.correction_rate ?? null;

  return (
    <DataState
      loading={accuracy.loading}
      errorMessage={accuracy.error?.message}
      errorTitle="Accuracy reporting is not available to you"
      isEmpty={data === null}
      emptyTitle="Nothing has been classified"
    >
      <div className="space-y-6">
        <Notice tone="info" title="The gate">
          {data?.gate}
        </Notice>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Kpi label="Messages classified" value={data?.messages ?? 0} />
          <Kpi
            label="Correction rate"
            value={percent(correction)}
            tone={(correction ?? 0) > 0.2 ? "warn" : "neutral"}
          />
          <Kpi
            label="Auto-issued and unreviewed"
            value={unreviewed}
            tone={unreviewed > 0 ? "warn" : "neutral"}
            detail="Tier 1 documents in the monthly quality sample"
          />
        </div>

        <Card>
          <CardHeader
            title="Accuracy per classification category"
            subtitle="A correction is a false positive for the suggested category and a false negative for the one Legal chose."
          />
          <div className="table-scroll">
            <div className="min-w-[47.5rem]">
              <Row cols={ACCURACY_COLS} head>
                <div>Category</div>
                <div>Suggested</div>
                <div>Confirmed</div>
                <div>False positive</div>
                <div>False negative</div>
                <div>Precision</div>
              </Row>
              <DataState
                loading={false}
                isEmpty={categories.length === 0}
                emptyTitle="Nothing has been classified in this window"
              >
                {categories.map((row) => (
                  <Row key={row.category} cols={ACCURACY_COLS}>
                    <div className="text-sm">{titleCase(row.category)}</div>
                    <div className="text-sm">{row.suggested}</div>
                    <div className="text-sm">{row.confirmed}</div>
                    <div className="text-sm">{row.false_positive}</div>
                    <div className="text-sm">{row.false_negative}</div>
                    <div>
                      <PrecisionCell value={row.precision} />
                    </div>
                  </Row>
                ))}
              </DataState>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Monthly quality sample"
            subtitle="Every tier 1 document issued without a drafting cycle lands here for review."
          />
          <div className="table-scroll">
            <div className="min-w-[45rem]">
              <Row cols={SAMPLE_COLS} head>
                <div>Period</div>
                <div>Why it is in the sample</div>
                <div>Issued</div>
                <div>Reviewed</div>
              </Row>
              <DataState
                loading={sample.loading}
                errorMessage={sample.error?.message}
                errorTitle="The quality sample is not available to you"
                isEmpty={samples.length === 0}
                emptyTitle="Nothing has been auto-issued"
              >
                {samples.map((row) => (
                  <Row key={row.id} cols={SAMPLE_COLS}>
                    <div className="text-sm">{row.period}</div>
                    <div className="text-sm">{row.reason}</div>
                    <div className="text-sm">{formatDate(row.created_at)}</div>
                    <div>
                      <Pill tone={row.reviewed ? "good" : "warn"}>
                        {row.reviewed ? titleCase(row.outcome ?? "reviewed") : "Awaiting review"}
                      </Pill>
                    </div>
                  </Row>
                ))}
              </DataState>
            </div>
          </div>
        </Card>
      </div>
    </DataState>
  );
}

const TABS = [
  { id: "kpi", label: "Improvement" },
  { id: "exposure", label: "Risk and exposure" },
  { id: "patterns", label: "Deviation patterns" },
  { id: "accuracy", label: "Accuracy" },
];

const VIEWS: Record<string, (props: { entity: string }) => React.ReactElement> = {
  kpi: Improvement,
  exposure: Exposure,
  patterns: Patterns,
  accuracy: Accuracy,
};

export default function Metrics() {
  const { entity } = useSession();
  const [tab, setTab] = React.useState("kpi");
  const View = VIEWS[tab] ?? Improvement;

  return (
    <div className="space-y-6">
      <PageTitle
        title="Metrics"
        subtitle={
          "Improvement against baseline, exposure carried by the agreements we signed, and " +
          "the measured accuracy of every capability that runs."
        }
      />

      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      <View entity={entity} />
    </div>
  );
}
