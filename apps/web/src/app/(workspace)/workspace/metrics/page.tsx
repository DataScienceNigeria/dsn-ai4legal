"use client";

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
  Kpi,
  Modal,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Row,
  Tabs,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type {
  DeviationPattern,
  ExposureReport,
  InboxAccuracy,
  KpiRow,
  QualitySampleRow,
} from "@/lib/types";
import { cn, formatDate, percent, titleCase } from "@/lib/utils";

const KPI_COLS = "minmax(0,1fr) 6.5rem 7rem 5.5rem 6rem 4rem";
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

function unitSuffix(unit: string): string {
  return unit === "percent" || unit === "per cent" ? "%" : "";
}

/*
  Recording a baseline and a target.

  Both were seeded, and eight of the ten arrived empty, which left most of the
  table reading "not set" against a target nobody could be held to. Neither
  number is one a system can work out: the current figure comes from what
  actually happened, the baseline is what the team was doing before, and the
  target is what they have agreed to aim at. The last two are somebody's
  judgement, so somebody has to be able to write them down.

  The capture date is stamped rather than asked for. It is the date the reading
  was entered, and a reading entered today did not come from last quarter.
*/
function EditBaseline({ row, onSaved }: Readonly<{ row: KpiRow; onSaved: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [baseline, setBaseline] = React.useState(row.baseline?.toString() ?? "");
  const [target, setTarget] = React.useState(row.phase_1_target?.toString() ?? "");

  const save = useAction(async () => {
    await api(`/reports/kpi/${row.code}`, {
      method: "PUT",
      body: {
        baseline_value: baseline === "" ? null : Number(baseline),
        target: target === "" ? null : Number(target),
        clear_baseline: baseline === "",
      },
    });
    setOpen(false);
    onSaved();
  });

  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        {row.baseline === null ? "Set" : "Edit"}
      </Button>
      <Modal
        open={open}
        title={row.name}
        subtitle={row.measurement_method}
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={save.busy} onClick={() => void save.run()}>
              Record it
            </Button>
          </>
        }
      >
        {save.error ? (
          <Refusal
            title="That was not recorded"
            reason={save.error.message}
            reasons={save.error.reasons}
          />
        ) : null}

        <Notice tone="info" title="The current figure is not editable">
          {row.current === null
            ? "The platform does not measure this one yet, so the current column stays empty whatever is set here."
            : `The platform measures it from what happened: ${row.current}${unitSuffix(row.unit)} at the moment.`}
        </Notice>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={`Baseline, ${row.unit}`}
            hint="What the team was doing before. Leave empty to clear it."
          >
            <Input
              type="number"
              min={0}
              step="any"
              value={baseline}
              onChange={(event) => setBaseline(event.target.value)}
            />
          </Field>
          <Field
            label={`Target, ${row.unit}`}
            hint={row.direction === "down" ? "Lower is better." : "Higher is better."}
          >
            <Input
              type="number"
              min={0}
              step="any"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
            />
          </Field>
        </div>

        {row.baseline_captured_on ? (
          <p className="text-xs text-muted-foreground">
            {`The current baseline was recorded on ${formatDate(row.baseline_captured_on)}. Saving a new figure stamps today.`}
          </p>
        ) : null}
      </Modal>
    </>
  );
}

function Measure({
  row,
  canEdit,
  onSaved,
}: Readonly<{ row: KpiRow; canEdit: boolean; onSaved: () => void }>) {
  const suffix = unitSuffix(row.unit);
  const shown = row.current === null ? "Not measured" : `${row.current}${suffix}`;

  return (
    <Row cols={KPI_COLS}>
      {/*
        The code was the third line of every row and nobody reads it. It names
        a KPI in a PRD, and the KPI is already named in full on the line above
        in the words the team uses for it. It stays on the record and off the
        screen.
      */}
      <div className="min-w-0">
        <div className="text-sm font-medium leading-snug">{row.name}</div>
        <div className="mt-0.5 text-xs leading-snug text-muted-foreground">
          {row.measurement_method}
        </div>
      </div>
      <div className="text-sm">
        {row.baseline === null ? (
          <span className="text-xs text-muted-foreground">Not set</span>
        ) : (
          <>
            {`${row.baseline}${suffix}`}
            {row.baseline_captured_on ? (
              <div className="text-xs text-muted-foreground">
                {formatDate(row.baseline_captured_on)}
              </div>
            ) : null}
          </>
        )}
      </div>
      <div className={cn("text-sm", row.current !== null && "font-medium")}>
        {row.current === null ? (
          <span className="text-xs text-muted-foreground">{shown}</span>
        ) : (
          shown
        )}
      </div>
      <div className="text-sm">
        {row.phase_1_target === null ? (
          <span className="text-xs text-muted-foreground">Not set</span>
        ) : (
          `${row.phase_1_target}${suffix}`
        )}
      </div>
      <div>
        <Pill tone={trackTone(row.on_track)}>{trackLabel(row.on_track)}</Pill>
      </div>
      <div className="text-right">
        {canEdit ? <EditBaseline row={row} onSaved={onSaved} /> : null}
      </div>
    </Row>
  );
}

function Improvement({ entity }: Readonly<{ entity: string }>) {
  const { has } = useRoles();
  const kpis = useApi<KpiRow[]>("/reports/kpi", [entity]);
  const rows = kpis.data ?? [];

  // Setting the number the team is measured against is the lead's, like every
  // other decision the team is then held to.
  const canEdit = has("head_of_legal", "admin");
  const unset = rows.filter((row) => row.baseline === null).length;

  return (
    <div className="space-y-4">
      {unset > 0 ? (
        <Notice
          tone="warn"
          title={`${unset} of ${rows.length} measures have no baseline`}
        >
          {canEdit
            ? "A target is not accepted as met without one, so those rows report no reading whatever the platform measures. Set on the row."
            : "A target is not accepted as met without one. The legal lead records them."}
        </Notice>
      ) : null}

      <Card>
        <CardHeader
          title="Every KPI against baseline and target"
          subtitle="The measurement definition sits beside each figure, so the number can be argued with."
        />
        <div className="table-scroll">
          <div className="min-w-[68rem]">
            <Row cols={KPI_COLS} head>
              <div>Measure</div>
              <div>Baseline</div>
              <div>Current</div>
              <div>Target</div>
              <div>Status</div>
              <div className="text-right">{canEdit ? "Record" : ""}</div>
            </Row>
            <DataState
              loading={kpis.loading}
              errorMessage={kpis.error?.message}
              errorTitle="KPIs are not available to you"
              isEmpty={rows.length === 0}
              emptyTitle="No measure is in the register"
            >
              {rows.map((row) => (
                <Measure key={row.code} row={row} canEdit={canEdit} onSaved={kpis.reload} />
              ))}
            </DataState>
          </div>
        </div>
      </Card>
    </div>
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
          <div className="grid gap-3 sm:grid-cols-2">
            <Kpi label="Deviations accepted" value={data.deviations_accepted} />
            <Kpi
              label="Unusual liability positions"
              value={data.unusual_liability_positions.length}
              tone={data.unusual_liability_positions.length > 0 ? "warn" : "neutral"}
            />
          </div>

          <Notice tone="info" title="What this counts">
            {data.note}
          </Notice>

          <ConcededClauses report={data} />

          {/*
            Obligations falling due were counted here and are not exposure.
            This tab answers what we agreed to that was not our position; an
            obligation inside its notice period is work nobody has done yet,
            which is a different question wearing the same clothes. The
            deadlines that are legal's own reach the calendar feed and the
            reminders instead.
          */}
          <Card>
            <CardHeader
              title="Contracts on an unusual liability position"
              subtitle="A critical or material liability deviation was accepted, or the agreement carries no limitation at all."
            />
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
        subtitle="A concession rate appears only once a finding has been decided, so undecided points do not flatter it."
      />
      <div className="table-scroll">
        <div className="min-w-[51.25rem]">
          <Row cols={PATTERN_COLS} head>
            <div>Clause</div>
            <div>Counterparty class</div>
            <div>Challenged</div>
            <div>Accepted</div>
            <div>Rejected</div>
            <div>Undecided</div>
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
                <div className={cn("text-sm", row.undecided > 0 && "text-warning")}>
                  {row.undecided}
                </div>
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

/*
  The tabs stop offering doors that will not open.

  Every one of these views is a separate endpoint with its own role gate, and
  the tab strip used to render all four to everybody. Whoever could not read a
  view found out by clicking it and being refused, which is the worst place to
  learn it: after the request, with an error where the answer should be.
*/
const TABS = [
  { id: "kpi", label: "Improvement", roles: ["counsel", "head_of_legal", "management", "admin", "auditor"] },
  { id: "exposure", label: "Risk and exposure", roles: ["counsel", "head_of_legal", "admin", "auditor"] },
  { id: "patterns", label: "Deviation patterns", roles: ["counsel", "head_of_legal", "admin", "auditor"] },
  { id: "accuracy", label: "Accuracy", roles: ["counsel", "head_of_legal", "admin", "auditor"] },
];

const VIEWS: Record<string, (props: { entity: string }) => React.ReactElement> = {
  kpi: Improvement,
  exposure: Exposure,
  patterns: Patterns,
  accuracy: Accuracy,
};

export default function Metrics() {
  const { entity } = useSession();
  const { has } = useRoles();

  const tabs = TABS.filter((one) => has(...one.roles));
  const [tab, setTab] = React.useState(tabs[0]?.id ?? "kpi");
  const active = tabs.some((one) => one.id === tab) ? tab : (tabs[0]?.id ?? "kpi");
  const View = VIEWS[active] ?? Improvement;

  if (tabs.length === 0) {
    return <Refusal title="Metrics are not available to you" />;
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="Metrics"
        subtitle={
          "Improvement against baseline, exposure carried by the agreements we signed, and " +
          "the measured accuracy of every capability that runs."
        }
      />

      {tabs.length > 1 ? (
        <Tabs
          tabs={tabs.map(({ id, label }) => ({ id, label }))}
          active={active}
          onChange={setTab}
        />
      ) : null}
      <View entity={entity} />
    </div>
  );
}
