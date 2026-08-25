"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { AssessmentActions } from "@/components/app/assessment-actions";
import { useSession } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
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
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Assessment } from "@/lib/types";
import { cn, formatDate, titleCase } from "@/lib/utils";

const STAGE_ORDER = ["product", "engineering", "legal", "business_owner"];

/*
  Legal raises assessments too.

  There is no data protection officer role any more, which means legal is the
  officer. An officer who can only score somebody else's assessment and never
  open one for their own work is half a job, and legal builds things that touch
  personal data like every other department does. The form is the same one the
  department leads fill in, so it is the same screen.
*/
export default function Assessments() {
  const { entity } = useSession();
  const router = useRouter();
  const { data, loading, error, reload } = useApi<Assessment[]>("/assessments", [entity]);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [starting, setStarting] = React.useState(false);
  const [project, setProject] = React.useState("");

  const start = useAction(async () => {
    const created = await api<Assessment>("/assessments/dpia", {
      method: "POST",
      body: { project_name: project.trim() },
    });
    router.push(`/portal/assessments/${created.id}`);
  });

  const current = data?.find((item) => item.id === selectedId) ?? data?.[0] ?? null;

  if (error) {
    return <Refusal title="Assessments are not available to you" reason={error.message} />;
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="Privacy and AI assessments"
        subtitle={
          "Assessment is a workflow with stages, owners, evidence and an accountable owner, " +
          "not a form completed at the end."
        }
        actions={
          <Button variant="primary" onClick={() => setStarting(true)}>
            Start a DPIA
          </Button>
        }
      />

      <Modal
        open={starting}
        title="Start a data protection assessment"
        subtitle="Name the thing being built. Everything else is saved as you write it."
        onClose={() => setStarting(false)}
        footer={
          <>
            <Button onClick={() => setStarting(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={project.trim().length < 3 || start.busy}
              onClick={() => void start.run()}
            >
              Start it
            </Button>
          </>
        }
      >
        {start.error ? (
          <Refusal title="That could not be started" reason={start.error.message} />
        ) : null}
        <Field label="Project or product name" required>
          <Input
            value={project}
            onChange={(event) => setProject(event.target.value)}
            placeholder="EqualyzAI Voice Agents"
          />
        </Field>
      </Modal>

      {loading ? (
        <Spinner />
      ) : !data?.length ? (
        <Empty title="No assessment is open in this entity" />
      ) : (
        <div className="grid gap-4 lg:gap-5 lg:grid-cols-[17rem_minmax(0,1fr)]">
          <Card>
            <CardHeader title="Assessments" />
            <div>
              {data.map((assessment) => (
                <button
                  key={assessment.id}
                  onClick={() => setSelectedId(assessment.id)}
                  className={cn(
                    "block w-full border-b px-4 py-3 text-left last:border-b-0 hover:bg-muted/60",
                    current?.id === assessment.id && "bg-muted",
                  )}
                >
                  {/*
                    Through to the assessment itself. A list of titles is not a
                    place to assess one, and the DPIA is where the answers and
                    the judgement sit beside each other.
                  */}
                  <Link
                    href={`/workspace/assessments/${assessment.id}`}
                    className="block text-sm font-medium no-underline hover:underline"
                  >
                    {assessment.title}
                  </Link>
                  <div className="mt-1 flex items-center gap-1.5">
                    <Mono>{assessment.reference}</Mono>
                    <Pill tone={assessment.stage === "closed" ? "good" : "warn"}>
                      {titleCase(assessment.stage)}
                    </Pill>
                  </div>
                </button>
              ))}
            </div>
          </Card>

          {current ? (
            <div className="space-y-4">
              <Card>
                <CardHeader
                  title={current.title}
                  subtitle={
                    <span className="flex flex-wrap items-center gap-2">
                      <Mono>{current.reference}</Mono>
                      <Pill tone="info">{titleCase(current.assessment_type)}</Pill>
                      <span>Review due {formatDate(current.review_date)}</span>
                    </span>
                  }
                  actions={<AssessmentActions assessment={current} onChanged={reload} />}
                />
                <CardBody>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {STAGE_ORDER.map((stage) => {
                      const record = current.stage_records.find((item) => item.stage === stage);
                      const done = record?.status === "complete";
                      const active = current.stage === stage;
                      return (
                        <div
                          key={stage}
                          className={cn(
                            "flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs",
                            done && "border-primary/30 bg-primary/10 text-primary",
                            active && "border-warning/40 bg-warning/10",
                          )}
                        >
                          <span aria-hidden>{done ? "✓" : active ? "→" : "○"}</span>
                          {titleCase(stage)}
                        </div>
                      );
                    })}
                  </div>
                </CardBody>
              </Card>

              {current.residual_risk_decision ? (
                <Notice tone="good" title="Residual risk decided">
                  {titleCase(current.residual_risk_decision)}. {current.residual_risk_reason}
                </Notice>
              ) : (
                <Notice tone="warn" title="Residual risk is not yet assigned">
                  The platform will not close an assessment with an unassigned residual risk. A
                  named accountable owner must accept, mitigate or escalate it, with a reason.
                </Notice>
              )}

              <div className="grid gap-4 lg:grid-cols-2">
                <Card>
                  <CardHeader title="Identified risks" />
                  <div>
                    {current.risks.map((risk) => (
                      <div key={risk.risk} className="border-b p-4 last:border-b-0">
                        <div className="text-sm font-medium">{risk.risk}</div>
                        <div className="mt-1.5 flex gap-1.5">
                          <Pill tone="neutral">Likelihood {risk.likelihood}</Pill>
                          <Pill tone={risk.impact === "high" ? "bad" : "warn"}>
                            Impact {risk.impact}
                          </Pill>
                        </div>
                        <div className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                          Control: {risk.control}
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>

                <Card>
                  <CardHeader title="Conditions" subtitle="Outstanding conditions become tracked tasks on close" />
                  <div>
                    {current.conditions.length ? (
                      current.conditions.map((condition) => (
                        <Row key={condition.name} cols="minmax(0,1fr) 6.25rem">
                          <div>
                            <div className="text-sm">{condition.name}</div>
                            <div className="text-xs text-muted-foreground">{condition.detail}</div>
                          </div>
                          <div>
                            <Pill tone={condition.satisfied ? "good" : "warn"}>
                              {condition.satisfied ? "Satisfied" : "Outstanding"}
                            </Pill>
                          </div>
                        </Row>
                      ))
                    ) : (
                      <Empty title="No conditions recorded" />
                    )}
                  </div>
                </Card>
              </div>

              <Card>
                <CardHeader title="What was captured" />
                <CardBody>
                  <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
                    {Object.entries(current.captured).map(([key, value]) => (
                      <div key={key}>
                        <dt className="text-xs text-muted-foreground">{titleCase(key)}</dt>
                        <dd className="text-sm leading-relaxed">{String(value ?? "")}</dd>
                      </div>
                    ))}
                  </dl>
                </CardBody>
              </Card>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
