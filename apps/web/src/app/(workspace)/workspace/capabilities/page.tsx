"use client";

import * as React from "react";

import { CapabilityStatePill } from "@/components/app/status";
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
  name: string;
  version: number;
  description: string | null;
  cases: GoldenCase[];
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
  The gate is only a control if something measures it. This runs the capability
  over its golden set, scores it by the metric the register names, and lets the
  result act: below the gate, the capability switches itself off everywhere.
*/
function Evaluation({
  capability,
  onChanged,
}: Readonly<{ capability: Capability; onChanged: () => void }>) {
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

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Evaluate
      </Button>
      <Modal
        open={open}
        title={`${capability.name}, evaluation`}
        subtitle={`${capability.metric_name}, ${capability.gate_expression}.`}
        width="lg"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Close</Button>
            <Button variant="primary" disabled={measure.busy} onClick={() => void measure.run()}>
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

        <Card>
          <CardHeader
            title="Golden set"
            subtitle={
              golden.data
                ? `${golden.data.name} version ${golden.data.version}, ${golden.data.cases.length} cases`
                : "The cases the gate is measured against."
            }
          />
          <CardBody>
            <DataState
              loading={golden.loading}
              errorMessage={golden.error?.message}
              errorTitle="No golden set exists for this capability"
              isEmpty={(golden.data?.cases ?? []).length === 0}
              emptyTitle="This set holds no cases"
            >
              <div className="space-y-2">
                {(golden.data?.cases ?? []).map((row) => (
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
  A case is added by the people who would otherwise argue about whether the
  answer was right. Writing the expected answer down is the argument, settled
  once, in a form a machine can check.
*/
function AddCase({ code, onDone }: Readonly<{ code: string; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [reference, setReference] = React.useState("");
  const [prompt, setPrompt] = React.useState("");
  const [expected, setExpected] = React.useState("{}");

  const add = useAction(async () => {
    await api(`/capabilities/${code}/golden-set/cases`, {
      method: "POST",
      body: { reference, prompt, expected: JSON.parse(expected) },
    });
    onDone();
    setOpen(false);
    setReference("");
    setPrompt("");
  });

  let valid = true;
  try {
    JSON.parse(expected);
  } catch {
    valid = false;
  }

  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        Add a case
      </Button>
      <Modal
        open={open}
        title="Add a golden case"
        subtitle="What goes in, and the answer a competent person would give. The scorer for this capability knows how to read the expected shape."
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!reference.trim() || !prompt.trim() || !valid || add.busy}
              onClick={() => void add.run()}
            >
              Add it
            </Button>
          </>
        }
      >
        <Field label="Reference" required>
          <Input value={reference} onChange={(event) => setReference(event.target.value)} />
        </Field>
        <Field label="Input" required>
          <Textarea
            className="min-h-[8rem]"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
          />
        </Field>
        <Field
          label="Expected"
          required
          error={valid ? null : "That is not valid JSON."}
          hint="JSON. For a classification set, {&quot;classification&quot;: &quot;action_required&quot;}."
        >
          <Textarea value={expected} onChange={(event) => setExpected(event.target.value)} />
        </Field>
        {add.error ? <Refusal title="That case was refused" reason={add.error.message} /> : null}
      </Modal>
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

  if (capability.state === "disabled") {
    return (
      <Button
        size="sm"
        variant="primary"
        disabled={busy || !capability.passes_gate}
        title={
          capability.passes_gate
            ? "Re-enable"
            : "It cannot be enabled while it is below its gate."
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

      <Card>
        <CardHeader
          title="Capability register"
          subtitle="A capability below its gate does not run, whatever anyone sets here."
        />
        <div className="table-scroll">
          <div className="min-w-[67.5rem]">
            <Row cols="minmax(0,1.3fr) 4.375rem 8.125rem 7.5rem 7.5rem 8.125rem minmax(0,1fr)" head>
              <div>Capability</div>
              <div>Module</div>
              <div>Metric</div>
              <div>Score</div>
              <div>Gate</div>
              <div>State</div>
              <div>Kill switch</div>
            </Row>

            {capabilities.loading ? (
              <Spinner />
            ) : (
              capabilities.data?.map((capability) => (
                <Row
                  key={capability.id}
                  cols="minmax(0,1.3fr) 4.375rem 8.125rem 7.5rem 7.5rem 8.125rem minmax(0,1fr)"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{capability.name}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      Confirmed by {titleCase(capability.confirming_role)}, up to{" "}
                      {titleCase(capability.max_data_class)}
                    </div>
                  </div>
                  <Mono>{capability.module}</Mono>
                  <div className="text-xs">{capability.metric_name}</div>
                  <div>
                    <Pill tone={capability.passes_gate ? "good" : "bad"}>
                      {capability.last_score_label ?? capability.last_score ?? "Not measured"}
                    </Pill>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {capability.gate_threshold ?? "None"}
                  </div>
                  <div>
                    <CapabilityStatePill
                      state={capability.state}
                      passesGate={capability.passes_gate}
                    />
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
                      onChanged={() => {
                        capabilities.reload();
                        quality.reload();
                      }}
                    />
                    {canToggle ? (
                      <AddCase
                        code={capability.code}
                        onDone={() => capabilities.reload()}
                      />
                    ) : null}
                    <span className="text-xs text-muted-foreground">
                      {formatDate(capability.last_evaluated_at)}
                    </span>
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
