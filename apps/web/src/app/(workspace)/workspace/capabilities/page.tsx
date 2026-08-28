"use client";

import * as React from "react";

import { CapabilityStatePill } from "@/components/app/status";
import { StepUpGate } from "@/components/app/step-up";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  DataState,
  Empty,
  Field,
  Input,
  Modal,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Row,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useRoles } from "@/components/app/session";
import { useAction, useApi } from "@/lib/hooks";
import type { AiInteraction, Capability } from "@/lib/types";
import { formatDate, titleCase } from "@/lib/utils";

type QualityRow = {
  capability: string;
  state: string;
  calls: number;
  accepted: number;
  edited: number;
  rejected: number;
  correction_rate: number | null;
  cost_usd: number;
  median_latency_ms: number | null;
  gate_threshold: number | null;
  gate_enforced: boolean;
  gate_status: string;
  last_score: number | null;
  disabled_reason: string | null;
};

type GoldenCase = {
  id: string;
  reference: string;
  prompt: string;
  expected: Record<string, unknown>;
  notes: string | null;
  active: boolean;
};

type GoldenSet = {
  id: string | null;
  name: string;
  version: number;
  description: string | null;
  cases: GoldenCase[];
  expected_shape: Record<string, unknown>;
  shape_note: string;
  measurable: boolean;
};

type EvaluationRun = {
  id: string;
  golden_set: string;
  set_size: number;
  score: number;
  score_label: string | null;
  threshold: number;
  passed: boolean;
  run_at: string;
  detail: { unrunnable?: number; cases?: { reference: string; passed: boolean; detail: string }[] };
};

/*
  The gate is only a reading if something measures it. This runs the capability
  over its golden set and scores it by the metric the register names. The
  result changes nothing on its own: a failure is shown to the people who own
  the capability, and they decide.
*/
function Evaluation({
  capability,
  canImport,
  onChanged,
}: Readonly<{ capability: Capability; canImport: boolean; onChanged: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const golden = useApi<GoldenSet>(
    open ? `/capabilities/${capability.code}/golden-set` : null,
    [capability.code, open],
  );
  const runs = useApi<EvaluationRun[]>(
    open ? `/capabilities/${capability.code}/evaluations` : null,
    [capability.code, open],
  );

  const measure = useAction(async () => {
    await api(`/capabilities/${capability.code}/run-evaluation`, { method: "POST" });
    golden.reload();
    runs.reload();
    onChanged();
  });

  const latest = runs.data?.[0];
  const set = golden.data ?? null;

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Evaluate
      </Button>
      <Modal
        open={open}
        title={`${capability.name}, evaluation`}
        subtitle={
          `${capability.metric_name}, ${capability.gate_expression}. ` +
          `Confirmed by ${titleCase(capability.confirming_role)}, up to ` +
          `${titleCase(capability.max_data_class)}.`
        }
        width="lg"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Close</Button>
            {canImport ? (
              <ImportSet
                code={capability.code}
                golden={set}
                onDone={() => {
                  golden.reload();
                  onChanged();
                }}
              />
            ) : null}
            <Button
              variant="primary"
              disabled={measure.busy || (set !== null && !set.measurable)}
              onClick={() => void measure.run()}
            >
              {measure.busy ? "Running the set" : "Run the golden set"}
            </Button>
          </>
        }
      >
        {measure.error ? (
          <Refusal
            title="Nothing was measured"
            reason={measure.error.message}
            reasons={Object.values(measure.error.fieldErrors)}
          />
        ) : null}

        {latest ? (
          <Notice
            tone={latest.passed ? "good" : "bad"}
            title={`${latest.score.toFixed(3)} against a gate of ${latest.threshold}`}
          >
            {latest.score_label}. Measured over {latest.set_size} cases on{" "}
            {formatDate(latest.run_at)}.
            {latest.detail?.unrunnable
              ? ` ${latest.detail.unrunnable} cases could not be run and were left out.`
              : ""}
          </Notice>
        ) : null}

        {set && !set.measurable ? (
          <Notice tone="warn" title="This capability has no scorer">
            {set.shape_note} Its gate is a statement about how it is used, not a number anything
            can take.
          </Notice>
        ) : null}

        {set && set.measurable && set.cases.length > 0 && set.cases.length < 10 ? (
          <Notice tone="warn" title={`This set holds ${set.cases.length} cases`}>
            A set this small moves in steps too large to read. One case failing out of three is a
            third of the score, so the number swings past most thresholds on a single clause.
            Import more before treating it as a control.
          </Notice>
        ) : null}

        <Card>
          <CardHeader
            title="Golden set"
            subtitle={
              set && set.version > 0
                ? `${set.name} version ${set.version}, ${set.cases.length} cases`
                : "No set has been written for this capability yet."
            }
          />
          <CardBody>
            <DataState
              loading={golden.loading}
              errorMessage={golden.error?.message}
              errorTitle="The golden set could not be read"
              isEmpty={(set?.cases ?? []).length === 0}
              emptyTitle="This capability has no cases"
              emptyDetail="Import a file of cases to give its gate something to measure."
            >
              <div className="space-y-2">
                {(set?.cases ?? []).map((row) => (
                  <div key={row.id} className="rounded-md border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Mono>{row.reference}</Mono>
                      {latest?.detail?.cases?.find((c) => c.reference === row.reference) ? (
                        <Pill
                          tone={
                            latest.detail.cases.find((c) => c.reference === row.reference)?.passed
                              ? "good"
                              : "bad"
                          }
                        >
                          {latest.detail.cases.find((c) => c.reference === row.reference)?.detail}
                        </Pill>
                      ) : null}
                    </div>
                    <p className="mt-1.5 line-clamp-3 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                      {row.prompt}
                    </p>
                  </div>
                ))}
              </div>
            </DataState>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Every measurement taken" subtitle="Newest first" />
          <CardBody>
            <DataState
              loading={runs.loading}
              errorMessage={runs.error?.message}
              isEmpty={(runs.data ?? []).length === 0}
              emptyTitle="This capability has never been measured"
            >
              <div className="space-y-2">
                {(runs.data ?? []).map((run) => (
                  <div key={run.id} className="flex flex-wrap items-center gap-2 text-sm">
                    <Pill tone={run.passed ? "good" : "bad"}>{run.score.toFixed(3)}</Pill>
                    <span className="min-w-0 flex-1 truncate text-muted-foreground">
                      {run.score_label ?? run.golden_set}
                    </span>
                    <span className="text-xs text-muted-foreground">{formatDate(run.run_at)}</span>
                  </div>
                ))}
              </div>
            </DataState>
          </CardBody>
        </Card>
      </Modal>
    </>
  );
}

/*
  A set arrives whole. Cases are written together by the people who would
  otherwise argue about whether an answer was right, and a set assembled one
  box at a time is a set nobody reviewed. Each import lands as the next
  version, so a score taken last quarter still names the cases behind it.
*/
function ImportSet({
  code,
  golden,
  onDone,
}: Readonly<{ code: string; golden: GoldenSet | null; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [body, setBody] = React.useState("");
  const [name, setName] = React.useState("");
  const [keepExisting, setKeepExisting] = React.useState(true);
  const file = React.useRef<HTMLInputElement>(null);

  const template = React.useMemo(
    () =>
      JSON.stringify(
        {
          cases: [
            {
              reference: "GC-001",
              prompt: "The text, email or document the capability is given.",
              expected: golden?.expected_shape ?? {},
              notes: "Why a competent person would answer that way.",
            },
          ],
        },
        null,
        2,
      ),
    [golden?.expected_shape],
  );

  const parsed = React.useMemo(() => {
    if (!body.trim()) return { cases: null as unknown[] | null, error: null as string | null };
    try {
      const value = JSON.parse(body);
      const cases = Array.isArray(value) ? value : value?.cases;
      if (!Array.isArray(cases) || cases.length === 0) {
        return {
          cases: null,
          error: "That holds no cases. Give a list of cases, or an object with a cases list.",
        };
      }
      return { cases, error: null };
    } catch {
      return { cases: null, error: "That is not valid JSON." };
    }
  }, [body]);

  const send = useAction(async () => {
    await api(`/capabilities/${code}/golden-set/import`, {
      method: "POST",
      body: {
        cases: parsed.cases,
        keep_existing: keepExisting,
        ...(name.trim() ? { name: name.trim() } : {}),
      },
    });
    onDone();
    setOpen(false);
    setBody("");
  });

  const read = async (chosen: File | null) => {
    if (!chosen) return;
    setBody(await chosen.text());
  };

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Import cases
      </Button>
      <Modal
        open={open}
        title="Import golden cases"
        subtitle={
          golden && golden.version > 0
            ? `This lands as ${golden.name} version ${golden.version + 1}. The version in force now is left as it is, so the scores already taken against it still name their cases.`
            : "This creates the first version of the set."
        }
        width="lg"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!parsed.cases || send.busy}
              onClick={() => void send.run()}
            >
              {send.busy
                ? "Importing"
                : `Import ${parsed.cases ? parsed.cases.length : 0} cases`}
            </Button>
          </>
        }
      >
        {send.error ? (
          <Refusal
            title="Nothing was imported"
            reason={send.error.message}
            reasons={Object.values(send.error.fieldErrors)}
          />
        ) : null}

        <Field label="The file" error={parsed.error}>
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={file}
              type="file"
              accept=".json"
              className="hidden"
              onChange={(event) => void read(event.target.files?.[0] ?? null)}
            />
            <Button size="sm" onClick={() => file.current?.click()}>
              Choose a .json
            </Button>
            <span className="text-sm text-muted-foreground">
              {parsed.cases
                ? `${parsed.cases.length} cases read`
                : "Or paste the cases below"}
            </span>
          </div>
        </Field>

        <Field label="Cases" required hint={golden?.shape_note}>
          <Textarea
            className="min-h-[10rem] font-mono text-xs"
            placeholder={template}
            value={body}
            onChange={(event) => setBody(event.target.value)}
          />
        </Field>

        <Field label="What this capability expects">
          <pre className="overflow-x-auto rounded-md border bg-muted/40 p-3 text-xs leading-relaxed">
            {template}
          </pre>
        </Field>

        <Field label="Set name" hint="Leave it as it is to keep the name the set already carries.">
          <Input
            value={name}
            placeholder={golden?.name ?? code}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={keepExisting}
            onChange={(event) => setKeepExisting(event.target.checked)}
          />
          <span>
            Carry the cases already in the set into the new version. A case whose reference this
            import repeats is replaced rather than duplicated. Clear this to start the set again
            from what you are importing.
          </span>
        </label>
      </Modal>
    </>
  );
}

/*
  The gate is a number somebody set against a named metric, not a number
  written into a seed file. Both the old and the new gate go to the audit, so
  a score can be read against the gate that was in force when it was taken.
*/
function GateEditor({
  capability,
  onChanged,
}: Readonly<{ capability: Capability; onChanged: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [metric, setMetric] = React.useState(capability.metric_name);
  const [expression, setExpression] = React.useState(capability.gate_expression);
  const [threshold, setThreshold] = React.useState(
    capability.gate_threshold === null ? "" : String(capability.gate_threshold),
  );
  const [enforced, setEnforced] = React.useState(capability.gate_enforced);
  const [reason, setReason] = React.useState("");

  const value = threshold.trim() === "" ? null : Number(threshold);
  const badThreshold =
    value !== null && (Number.isNaN(value) || value < 0 || value > 1)
      ? "A threshold is a score between 0 and 1."
      : null;

  const save = useAction(async () => {
    await api(`/capabilities/${capability.code}/gate`, {
      method: "POST",
      body: {
        metric_name: metric,
        gate_expression: expression,
        gate_threshold: value,
        gate_enforced: enforced,
        reason,
      },
    });
    onChanged();
    setOpen(false);
    setReason("");
  });

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => {
          setMetric(capability.metric_name);
          setExpression(capability.gate_expression);
          setThreshold(
            capability.gate_threshold === null ? "" : String(capability.gate_threshold),
          );
          setEnforced(capability.gate_enforced);
          setOpen(true);
        }}
      >
        Gate
      </Button>
      <Modal
        open={open}
        title={`${capability.name}, gate`}
        subtitle="What is measured, where the line sits, and what happens when a run falls below it."
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!metric.trim() || reason.trim().length < 4 || !!badThreshold || save.busy}
              onClick={() => void save.run()}
            >
              {save.busy ? "Saving" : "Save the gate"}
            </Button>
          </>
        }
      >
        {save.error ? (
          <Refusal
            title="That gate was refused"
            reason={save.error.message}
            reasons={Object.values(save.error.fieldErrors)}
          />
        ) : null}

        <Field label="Metric" required hint="The name of the number, as the register reports it.">
          <Input value={metric} onChange={(event) => setMetric(event.target.value)} />
        </Field>

        <Field label="Gate" hint="How the line reads in words, for example at least 0.93 recall.">
          <Input value={expression} onChange={(event) => setExpression(event.target.value)} />
        </Field>

        <Field
          label="Threshold"
          error={badThreshold}
          hint="Leave it empty for a capability that is watched rather than gated. It scores 0 to 1."
        >
          <Input
            inputMode="decimal"
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
          />
        </Field>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={enforced}
            onChange={(event) => setEnforced(event.target.checked)}
          />
          <span>
            Stop calls while the last score is below the threshold. Worth having where the output
            goes somewhere nobody reads line by line. Where every item is confirmed one at a time,
            stopping the capability hands the reviewer an empty list instead of a reviewable one,
            which is the silent failure the gate exists to prevent.
          </span>
        </label>

        <Field label="Why" required hint="Recorded against the change, beside the old gate.">
          <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
      </Modal>
      <StepUpGate action="Changing a capability gate" state={save} />
    </>
  );
}

/*
  The kill switch. A capability below its gate cannot be turned back on from
  here, because the gate is the thing that decides, not the administrator.
*/
function KillSwitch({
  capability,
  canToggle,
  busy,
  onToggle,
}: Readonly<{
  capability: Capability;
  canToggle: boolean;
  busy: boolean;
  onToggle: (code: string, state: string, reason: string) => void;
}>) {
  if (!canToggle) {
    return <span className="text-xs text-muted-foreground">Read only for your role</span>;
  }

  const blocked = capability.gate_status === "failing" && capability.gate_enforced;

  if (capability.state === "disabled") {
    return (
      <Button
        size="sm"
        variant="primary"
        disabled={busy || blocked}
        title={
          blocked
            ? "It cannot be enabled while it is below an enforced gate. Measure it again."
            : "Re-enable"
        }
        onClick={() => onToggle(capability.code, "enabled", "Re-enabled after review.")}
      >
        Enable
      </Button>
    );
  }

  return (
    <Button
      size="sm"
      variant="destructive"
      disabled={busy}
      onClick={() =>
        onToggle(capability.code, "disabled", "Disabled by the administrator.")
      }
    >
      Disable now
    </Button>
  );
}

const GATE_TONE: Record<string, "good" | "warn" | "novel"> = {
  passing: "good",
  failing: "warn",
  not_measured: "novel",
};

export default function Capabilities() {
  const { has } = useRoles();
  const canToggle = has("admin", "head_of_legal");
  const capabilities = useApi<Capability[]>("/capabilities");
  const quality = useApi<QualityRow[]>("/reports/ai-quality");
  const interactions = useApi<AiInteraction[]>("/ai/interactions?limit=25");

  const toggle = useAction(async (code: string, state: string, reason: string) => {
    await api(`/capabilities/${code}/state`, { method: "POST", body: { state, reason } });
    capabilities.reload();
    quality.reload();
  });

  if (capabilities.error) {
    return (
      <Refusal title="The capability register is not available to you" reason={capabilities.error.message} />
    );
  }

  const disabled = (capabilities.data ?? []).filter((c) => c.state === "disabled");

  return (
    <div className="space-y-6">
      <PageTitle
        title="AI capabilities"
        subtitle={
          "Every AI use is a named capability with an owner, a data-class ceiling, a tier " +
          "ceiling, a route and a gate. Nothing runs as an unnamed model call."
        }
      />

      {disabled.length ? (
        <Notice tone="bad" title={`${disabled.length} capability disabled`}>
          {disabled.map((capability) => (
            <div key={capability.code} className="mt-1">
              <span className="font-medium">{capability.name}.</span> {capability.disabled_reason}
            </div>
          ))}
        </Notice>
      ) : null}

      {toggle.error ? <Refusal title="That change was refused" reason={toggle.error.message} /> : null}

      <StepUpGate action="Changing a capability state" state={toggle} />

      <Card>
        <CardHeader
          title="Capability register"
          subtitle={
            "A run records what a capability scored. Nothing switches itself off: where a gate " +
            "is set to stop calls, it stops them and says so, and every other failure waits for " +
            "somebody to act on it."
          }
        />
        <div className="table-scroll">
          <div className="min-w-[68rem]">
            <Row cols="minmax(0,1.9fr) 9rem 6.5rem 8.125rem 6.5rem minmax(0,15rem)" head>
              <div>Capability</div>
              <div>Score</div>
              <div>Gate</div>
              <div>State</div>
              <div>Measured</div>
              <div>Actions</div>
            </Row>

            {capabilities.loading ? (
              <Spinner />
            ) : (
              capabilities.data?.map((capability) => (
                <Row
                  key={capability.id}
                  cols="minmax(0,1.9fr) 9rem 6.5rem 8.125rem 6.5rem minmax(0,15rem)"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{capability.name}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {capability.metric_name}
                      {capability.gate_expression ? `, ${capability.gate_expression}` : ""}
                    </div>
                  </div>
                  <div>
                    <Pill tone={GATE_TONE[capability.gate_status] ?? "novel"}>
                      {capability.gate_status === "not_measured"
                        ? "Not yet measured"
                        : (capability.last_score_label ?? capability.last_score)}
                    </Pill>
                  </div>
                  <div className="text-xs">
                    <div className="text-muted-foreground">
                      {capability.gate_threshold ?? "Not gated"}
                    </div>
                    {capability.gate_threshold === null ? null : (
                      <div className="text-[11px] text-muted-foreground/80">
                        {capability.gate_enforced ? "Stops calls" : "Reported only"}
                      </div>
                    )}
                  </div>
                  <div>
                    <CapabilityStatePill
                      state={capability.state}
                      gateStatus={capability.gate_status}
                      enforced={capability.gate_enforced}
                    />
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {capability.last_evaluated_at ? formatDate(capability.last_evaluated_at) : "Never"}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <KillSwitch
                      capability={capability}
                      canToggle={canToggle}
                      busy={toggle.busy}
                      onToggle={toggle.run}
                    />
                    <Evaluation
                      capability={capability}
                      canImport={canToggle}
                      onChanged={() => {
                        capabilities.reload();
                        quality.reload();
                      }}
                    />
                    {canToggle ? (
                      <GateEditor
                        capability={capability}
                        onChanged={() => {
                          capabilities.reload();
                          quality.reload();
                        }}
                      />
                    ) : null}
                  </div>
                </Row>
              ))
            )}
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Usage and quality"
            subtitle="Human correction rate is the primary live quality signal."
          />
          <div>
            <Row cols="minmax(0,1fr) 4.375rem 6.875rem 5.625rem" head>
              <div>Capability</div>
              <div className="text-right">Calls</div>
              <div className="text-right">Correction rate</div>
              <div className="text-right">Cost</div>
            </Row>
            {quality.loading ? (
              <Spinner />
            ) : !quality.data?.length ? (
              <Empty title="No capability has been called yet" />
            ) : (
              quality.data.map((row) => (
                <Row key={row.capability} cols="minmax(0,1fr) 4.375rem 6.875rem 5.625rem">
                  <div className="truncate">{row.capability}</div>
                  <div className="text-right tabular-nums">{row.calls}</div>
                  <div className="text-right">
                    {row.correction_rate === null ? (
                      <span className="text-xs text-muted-foreground">No decisions</span>
                    ) : (
                      <Pill tone={row.correction_rate > 0.2 ? "warn" : "good"}>
                        {Math.round(row.correction_rate * 100)}%
                      </Pill>
                    )}
                  </div>
                  <div className="text-right tabular-nums text-xs">
                    ${row.cost_usd.toFixed(4)}
                  </div>
                </Row>
              ))
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Recent interactions" subtitle="Route, sources, and the human decision" />
          <div className="max-h-[420px] overflow-y-auto">
            {interactions.loading ? (
              <Spinner />
            ) : !interactions.data?.length ? (
              <Empty title="No interaction has been recorded" />
            ) : (
              interactions.data.map((interaction) => (
                <div key={interaction.id} className="border-b p-3 last:border-b-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-sm font-medium">
                      {titleCase(interaction.capability_code)}
                    </span>
                    {interaction.refused ? <Pill tone="bad">Refused</Pill> : null}
                    {interaction.shadow ? <Pill tone="novel">Shadow</Pill> : null}
                    {interaction.injection_detected ? (
                      <Pill tone="bad">Injection</Pill>
                    ) : null}
                    <Mono className="ml-auto">
                      {interaction.provider}, {interaction.retrieved_sources.length} sources
                    </Mono>
                  </div>
                  {interaction.refusal_reason ? (
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      {interaction.refusal_reason}
                    </p>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      <p className="text-xs leading-relaxed text-muted-foreground">
        No AI capability may send an external communication, alter permissions, publish a clause
        version, approve an item or trigger a signature request. Those actions are unavailable to
        the model layer by construction, not by instruction.
      </p>
    </div>
  );
}
