"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import { useRoles } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Field,
  Input,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Assessment, DpiaForm, DpiaQuestion } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

function visible(question: DpiaQuestion, answers: Record<string, unknown>): boolean {
  if (!question.depends_on) return true;
  const [key, expected] = question.depends_on.split("=");
  const given = answers[key];
  if (expected === "true") return given === true || String(given) === "true";
  return String(given).toLowerCase() === expected.toLowerCase();
}

function show(value: unknown): string {
  if (value === true) return "Yes";
  if (value === false) return "No";
  if (Array.isArray(value)) return value.join(", ");
  if (value === undefined || value === null || value === "") return "Not answered";
  return String(value);
}

/*
  Assessing a DPIA.

  The lead's answers on the left, the officer's judgement beside each section.
  Kept in one view rather than two screens, because an assessment of a section
  is a judgement about what that section says, and a reviewer who has to
  remember the answer while writing about it will write about what they
  remember.

  Nothing here can edit an answer. The record has to show what the team said,
  not what the officer wished they had said, and a section that reads well
  because the assessor rewrote it is not an assessment.
*/
export default function AssessDpia() {
  const params = useParams<{ assessmentId: string }>();
  const id = params.assessmentId;
  const { has } = useRoles();

  const form = useApi<DpiaForm>("/assessments/form/dpia");
  const record = useApi<Assessment>(`/assessments/${id}`, [id]);

  const canAssess = has("privacy", "head_of_legal", "admin");

  if (form.loading || record.loading) return <Spinner />;
  if (!form.data || !record.data) {
    return <Refusal title="That assessment is not available" reason={record.error?.message} />;
  }

  const answers = record.data.captured ?? {};
  const reviews = record.data.dpo_review ?? {};
  const assessable = form.data.sections.filter((section) => section.assessed);
  const outstanding = assessable.filter((section) => !reviews[section.key]);

  return (
    <div className="space-y-5">
      <PageTitle
        title={record.data.title}
        subtitle={
          record.data.submitted_at
            ? `Submitted ${formatDate(record.data.submitted_at)}. Assess each section, then decide.`
            : "Not yet submitted. The team is still writing it."
        }
        actions={
          <Link href="/workspace/assessments" className="no-underline">
            <Button size="sm">All assessments</Button>
          </Link>
        }
      />

      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <Mono>{record.data.reference}</Mono>
        <span>
          {assessable.length - outstanding.length} of {assessable.length} sections assessed
        </span>
      </div>

      {record.data.final_decision ? (
        <Notice
          tone={
            record.data.final_decision === "go_ahead"
              ? "good"
              : record.data.final_decision === "stop"
                ? "bad"
                : "warn"
          }
          title={
            form.data.decisions.find((one) => one.key === record.data?.final_decision)?.label ??
            record.data.final_decision
          }
        >
          {record.data.final_decision_reason}
          {record.data.review_date ? ` Review due ${formatDate(record.data.review_date)}.` : ""}
        </Notice>
      ) : null}

      {form.data.sections.map((section) => (
        <Card key={section.key}>
          <CardHeader
            title={section.title}
            subtitle={section.intent}
            actions={
              reviews[section.key] ? (
                <div className="flex items-center gap-2">
                  <Pill tone={reviews[section.key].adequate ? "good" : "warn"}>
                    {reviews[section.key].adequate ? "Adequate" : "Not adequate"}
                  </Pill>
                  <Pill
                    tone={
                      reviews[section.key].score >= 7
                        ? "good"
                        : reviews[section.key].score >= 4
                          ? "warn"
                          : "bad"
                    }
                  >
                    {reviews[section.key].score} of 10
                  </Pill>
                </div>
              ) : section.assessed ? (
                <Pill tone="neutral">Not assessed</Pill>
              ) : undefined
            }
          />
          <CardBody className="space-y-4">
            <dl className="space-y-3">
              {section.questions
                .filter((question) => visible(question, answers))
                .map((question) => (
                  <div key={question.key}>
                    <dt className="text-xs text-muted-foreground">{question.label}</dt>
                    <dd
                      className={cn(
                        "whitespace-pre-wrap text-sm leading-relaxed",
                        answers[question.key] === undefined && "italic text-muted-foreground",
                      )}
                    >
                      {show(answers[question.key])}
                    </dd>
                  </div>
                ))}
            </dl>

            {section.assessed && canAssess ? (
              <SectionAssessment
                assessmentId={id}
                section={section.key}
                existing={reviews[section.key]}
                onSaved={record.reload}
              />
            ) : null}
          </CardBody>
        </Card>
      ))}

      {canAssess && !record.data.final_decision ? (
        <FinalDecision
          assessmentId={id}
          decisions={form.data.decisions}
          outstanding={outstanding.map((section) => section.title)}
          onSaved={record.reload}
        />
      ) : null}
    </div>
  );
}

function SectionAssessment({
  assessmentId,
  section,
  existing,
  onSaved,
}: Readonly<{
  assessmentId: string;
  section: string;
  existing?: { adequate: boolean; reasons: string; score: number; recommendations: string | null; responsibility: string | null; due_date: string | null };
  onSaved: () => void;
}>) {
  const [open, setOpen] = React.useState(false);
  const [adequate, setAdequate] = React.useState(existing?.adequate ?? true);
  const [reasons, setReasons] = React.useState(existing?.reasons ?? "");
  const [score, setScore] = React.useState(String(existing?.score ?? 7));
  const [recommendations, setRecommendations] = React.useState(existing?.recommendations ?? "");
  const [responsibility, setResponsibility] = React.useState(existing?.responsibility ?? "");
  const [dueDate, setDueDate] = React.useState(existing?.due_date ?? "");

  const save = useAction(async () => {
    await api(`/assessments/${assessmentId}/sections/${section}/assessment`, {
      method: "POST",
      body: {
        adequate,
        reasons,
        score: Number(score),
        recommendations: recommendations || null,
        responsibility: responsibility || null,
        due_date: dueDate || null,
      },
    });
    setOpen(false);
    onSaved();
  });

  if (!open) {
    return (
      <div className="border-t pt-3">
        <Button size="sm" variant={existing ? "default" : "primary"} onClick={() => setOpen(true)}>
          {existing ? "Revise the assessment" : "Assess this section"}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4 border-t pt-4">
      {save.error ? (
        <Refusal title="That assessment was not recorded" reason={save.error.message} />
      ) : null}

      <div className="flex flex-wrap items-end gap-4">
        <Field label="Is the information adequate?">
          <div className="flex gap-2">
            <Button
              size="sm"
              variant={adequate ? "primary" : "default"}
              onClick={() => setAdequate(true)}
            >
              Adequate
            </Button>
            <Button
              size="sm"
              variant={!adequate ? "destructive" : "default"}
              onClick={() => setAdequate(false)}
            >
              Not adequate
            </Button>
          </div>
        </Field>

        <Field
          label="Score out of 10"
          hint="What the information is worth against what this section reasonably required."
        >
          <Input
            type="number"
            min={1}
            max={10}
            value={score}
            onChange={(event) => setScore(event.target.value)}
            className="w-24"
          />
        </Field>
      </div>

      <Field label="Reasons" required hint="Succinct and cogent. This is the record of the judgement.">
        <Textarea
          value={reasons}
          onChange={(event) => setReasons(event.target.value)}
          className="min-h-[5rem] leading-relaxed"
        />
      </Field>

      <Field label="Recommendations" hint="What has to change, if anything.">
        <Textarea
          value={recommendations}
          onChange={(event) => setRecommendations(event.target.value)}
          className="min-h-[4rem] leading-relaxed"
        />
      </Field>

      <div className="flex flex-wrap gap-4">
        <Field label="Responsible for it" hint="A recommendation with no owner is a wish.">
          <Input
            value={responsibility}
            onChange={(event) => setResponsibility(event.target.value)}
            placeholder="Head of Engineering"
          />
        </Field>
        <Field label="By when">
          <Input
            type="date"
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
          />
        </Field>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          variant="primary"
          disabled={reasons.trim().length < 5 || save.busy}
          onClick={() => void save.run()}
        >
          Record it
        </Button>
        <Button onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </div>
  );
}

function FinalDecision({
  assessmentId,
  decisions,
  outstanding,
  onSaved,
}: Readonly<{
  assessmentId: string;
  decisions: { key: string; label: string }[];
  outstanding: string[];
  onSaved: () => void;
}>) {
  const [decision, setDecision] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [reviewDate, setReviewDate] = React.useState("");

  const record = useAction(async () => {
    await api(`/assessments/${assessmentId}/decision`, {
      method: "POST",
      body: { decision, reason, review_date: reviewDate || null },
    });
    onSaved();
  });

  return (
    <Card>
      <CardHeader
        title="Final assessment"
        subtitle="Three outcomes and no fourth. Stop has to be available, or the assessment is a formality."
      />
      <CardBody className="space-y-4">
        {outstanding.length ? (
          <Notice tone="warn" title="Every section is assessed first">
            Still to assess: {outstanding.join(", ")}.
          </Notice>
        ) : null}

        {record.error ? (
          <Refusal
            title="That decision was not recorded"
            reason={record.error.message}
            reasons={record.error.reasons}
          />
        ) : null}

        <Field label="Decision" required>
          <Select value={decision} onChange={(event) => setDecision(event.target.value)}>
            <option value="">Choose an outcome</option>
            {decisions.map((one) => (
              <option key={one.key} value={one.key}>
                {one.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Reason" required>
          <Textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="min-h-[5rem] leading-relaxed"
          />
        </Field>

        <Field label="Review date" hint="When this assessment should be looked at again.">
          <Input
            type="date"
            value={reviewDate}
            onChange={(event) => setReviewDate(event.target.value)}
          />
        </Field>

        <Button
          variant="primary"
          disabled={!decision || reason.trim().length < 5 || outstanding.length > 0 || record.busy}
          onClick={() => void record.run()}
        >
          Record the decision
        </Button>
      </CardBody>
    </Card>
  );
}
