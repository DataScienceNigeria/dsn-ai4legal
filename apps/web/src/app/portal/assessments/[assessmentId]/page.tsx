"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

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
import type { Assessment, DpiaForm, DpiaQuestion, DpiaSection } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

const SAVE_AFTER_MS = 900;

function visible(question: DpiaQuestion, answers: Record<string, unknown>): boolean {
  if (!question.depends_on) return true;
  const [key, expected] = question.depends_on.split("=");
  const given = answers[key];
  if (expected === "true") return given === true || String(given) === "true";
  return String(given).toLowerCase() === expected.toLowerCase();
}

function answered(question: DpiaQuestion, answers: Record<string, unknown>): boolean {
  const value = answers[question.key];
  if (value === undefined || value === null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

/*
  Writing the assessment.

  One section at a time, in a rail on the left, because thirteen sections on one
  page is a wall that nobody starts. Each section says what it is for before it
  asks anything, and each question carries the tip from the template as help
  text, because the person filling this in has usually never written a DPIA and
  the tip is what tells them what a good answer looks like.

  Saved as it is typed. A DPIA is not filled in at one sitting: several
  questions need somebody else in the building to answer, and losing a morning
  to a closed tab is how a form stops being filled in at all.
*/
export default function PortalAssessment() {
  const params = useParams<{ assessmentId: string }>();
  const id = params.assessmentId;

  const form = useApi<DpiaForm>("/assessments/form/dpia");
  const record = useApi<Assessment>(`/assessments/${id}`, [id]);

  const [answers, setAnswers] = React.useState<Record<string, unknown>>({});
  const [active, setActive] = React.useState(0);
  const [saved, setSaved] = React.useState<"idle" | "saving" | "saved" | "failed">("idle");
  const loaded = React.useRef(false);

  React.useEffect(() => {
    if (loaded.current || !record.data) return;
    setAnswers({ ...record.data.captured });
    loaded.current = true;
  }, [record.data]);

  const locked = Boolean(record.data?.submitted_at);

  /*
    Saving after the typing stops rather than on every keystroke. A DPIA answer
    is a paragraph, and a request per character is a request per character.
  */
  const pending = React.useRef<Record<string, unknown> | null>(null);
  React.useEffect(() => {
    if (!loaded.current || locked || !pending.current) return;
    const body = pending.current;
    const timer = setTimeout(async () => {
      setSaved("saving");
      try {
        await api(`/assessments/${id}/answers`, { method: "PATCH", body: { answers: body } });
        setSaved("saved");
        pending.current = null;
      } catch {
        setSaved("failed");
      }
    }, SAVE_AFTER_MS);
    return () => clearTimeout(timer);
  }, [answers, id, locked]);

  function set(key: string, value: unknown) {
    setAnswers((was) => {
      const next = { ...was, [key]: value };
      pending.current = next;
      return next;
    });
  }

  const submit = useAction(async () => {
    await api(`/assessments/${id}/submit`, { method: "POST" });
    record.reload();
  });

  if (form.loading || record.loading) return <Spinner />;
  if (!form.data || !record.data) {
    return <Refusal title="That assessment is not available" reason={record.error?.message} />;
  }

  const sections = form.data.sections;
  const section = sections[active];

  const outstanding = sections.flatMap((each) =>
    each.questions
      .filter((question) => question.required && visible(question, answers))
      .filter((question) => !answered(question, answers))
      .map((question) => `${each.title}: ${question.label}`),
  );

  return (
    <div className="space-y-5">
      <PageTitle
        title={record.data.title}
        subtitle={
          record.data.final_decision
            ? "Assessed and decided. This is the record of what was asked and what was concluded."
            : locked
              ? "With the data protection officer. You will be told what they decide."
              : "Answer what you can. Everything is saved as you write it."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/portal/assessments" className="no-underline">
              <Button size="sm">All assessments</Button>
            </Link>
            {!locked ? (
              <Button
                size="sm"
                variant="primary"
                disabled={submit.busy || outstanding.length > 0}
                onClick={() => void submit.run()}
                title={
                  outstanding.length
                    ? `${outstanding.length} answers still needed`
                    : "Send it to the data protection officer"
                }
              >
                Submit for assessment
              </Button>
            ) : null}
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <Mono>{record.data.reference}</Mono>
        {locked ? (
          <Pill tone="info">Submitted {formatDate(record.data.submitted_at)}</Pill>
        ) : (
          <span>
            {saved === "saving"
              ? "Saving"
              : saved === "saved"
                ? "Saved"
                : saved === "failed"
                  ? "Not saved. Check your connection."
                  : ""}
          </span>
        )}
        {outstanding.length && !locked ? (
          <span>{outstanding.length} answers still needed</span>
        ) : null}
      </div>

      {submit.error ? (
        <Refusal
          title="Not ready to submit"
          reason={submit.error.message}
          reasons={submit.error.reasons}
        />
      ) : null}

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

      <div className="grid gap-5 lg:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
        <SectionRail
          sections={sections}
          active={active}
          answers={answers}
          onSelect={setActive}
        />

        <div className="space-y-4">
          <Card>
            <CardHeader title={section.title} subtitle={section.intent} />
            <CardBody className="space-y-5">
              {section.questions.filter((question) => visible(question, answers)).map((question) => (
                <QuestionField
                  key={question.key}
                  question={question}
                  value={answers[question.key]}
                  readOnly={locked}
                  onChange={(value) => set(question.key, value)}
                />
              ))}
            </CardBody>
          </Card>

          {/*
            The officer's judgement on this section, once there is one. Shown
            to the lead who wrote it, because a recommendation nobody reads is
            a recommendation nobody acts on.
          */}
          {record.data.dpo_review?.[section.key] ? (
            <Review review={record.data.dpo_review[section.key]} />
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button disabled={active === 0} onClick={() => setActive((was) => was - 1)}>
              Previous section
            </Button>
            <Button
              variant="primary"
              disabled={active === sections.length - 1}
              onClick={() => setActive((was) => was + 1)}
            >
              Next section
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function SectionRail({
  sections,
  active,
  answers,
  onSelect,
}: Readonly<{
  sections: DpiaSection[];
  active: number;
  answers: Record<string, unknown>;
  onSelect: (index: number) => void;
}>) {
  return (
    <nav aria-label="Assessment sections">
      <ol className="space-y-0.5 lg:sticky lg:top-6">
        {sections.map((section, index) => {
          const required = section.questions.filter(
            (question) => question.required && visible(question, answers),
          );
          const done = required.filter((question) => answered(question, answers)).length;
          const complete = required.length > 0 && done === required.length;

          return (
            <li key={section.key}>
              <button
                type="button"
                onClick={() => onSelect(index)}
                aria-current={index === active ? "step" : undefined}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm transition-colors",
                  index === active
                    ? "bg-heading/10 font-medium text-heading"
                    : "text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground",
                )}
              >
                <span
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-2xs tabular-nums",
                    complete
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border",
                  )}
                  aria-hidden
                >
                  {complete ? "✓" : index + 1}
                </span>
                <span className="min-w-0 flex-1 truncate">{section.title}</span>
                {required.length ? (
                  <span className="shrink-0 text-2xs tabular-nums text-muted-foreground">
                    {done}/{required.length}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function QuestionField({
  question,
  value,
  readOnly,
  onChange,
}: Readonly<{
  question: DpiaQuestion;
  value: unknown;
  readOnly: boolean;
  onChange: (value: unknown) => void;
}>) {
  const chosen = Array.isArray(value) ? (value as string[]) : [];

  return (
    <Field label={question.label} hint={question.help_text ?? undefined} required={question.required}>
      {question.kind === "long_text" ? (
        <Textarea
          value={String(value ?? "")}
          readOnly={readOnly}
          onChange={(event) => onChange(event.target.value)}
          className="min-h-[6rem] leading-relaxed"
        />
      ) : question.kind === "boolean" ? (
        <div className="flex gap-2">
          {[
            { label: "Yes", state: true },
            { label: "No", state: false },
          ].map((option) => (
            <Button
              key={option.label}
              size="sm"
              variant={value === option.state ? "primary" : "default"}
              disabled={readOnly}
              onClick={() => onChange(option.state)}
            >
              {option.label}
            </Button>
          ))}
        </div>
      ) : question.kind === "choice" ? (
        <Select
          value={String(value ?? "")}
          disabled={readOnly}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Choose one</option>
          {question.options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </Select>
      ) : question.kind === "multi_choice" ? (
        <div className="flex flex-wrap gap-1.5">
          {question.options.map((option) => {
            const on = chosen.includes(option);
            return (
              <Button
                key={option}
                size="sm"
                variant={on ? "primary" : "default"}
                disabled={readOnly}
                onClick={() =>
                  onChange(on ? chosen.filter((each) => each !== option) : [...chosen, option])
                }
              >
                {option}
              </Button>
            );
          })}
        </div>
      ) : (
        <Input
          type={question.kind === "date" ? "date" : "text"}
          value={String(value ?? "")}
          readOnly={readOnly}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </Field>
  );
}

function Review({
  review,
}: Readonly<{
  review: {
    adequate: boolean;
    reasons: string;
    score: number;
    recommendations: string | null;
    responsibility: string | null;
    due_date: string | null;
    assessed_by: string;
  };
}>) {
  return (
    <Card>
      <CardHeader
        title="The data protection officer's assessment"
        subtitle={`Assessed by ${review.assessed_by}`}
        actions={
          <div className="flex items-center gap-2">
            <Pill tone={review.adequate ? "good" : "warn"}>
              {review.adequate ? "Adequate" : "Not adequate"}
            </Pill>
            <Pill tone={review.score >= 7 ? "good" : review.score >= 4 ? "warn" : "bad"}>
              {review.score} of 10
            </Pill>
          </div>
        }
      />
      <CardBody className="space-y-3 text-sm leading-relaxed">
        <p>{review.reasons}</p>
        {review.recommendations ? (
          <div className="rounded-md border bg-muted/30 p-3">
            <div className="mb-1 text-2xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              Recommended
            </div>
            <p>{review.recommendations}</p>
            {review.responsibility || review.due_date ? (
              <p className="mt-1.5 text-xs text-muted-foreground">
                {review.responsibility ? `${review.responsibility}. ` : ""}
                {review.due_date ? `By ${formatDate(review.due_date)}.` : ""}
              </p>
            ) : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
