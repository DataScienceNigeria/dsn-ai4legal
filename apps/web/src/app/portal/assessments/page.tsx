"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

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
  Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Assessment } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const DECISION_TONE: Record<string, "good" | "warn" | "bad"> = {
  go_ahead: "good",
  modify: "warn",
  stop: "bad",
};

const DECISION_LABEL: Record<string, string> = {
  go_ahead: "Go ahead",
  modify: "Modify first",
  stop: "Stopped",
};

function state(assessment: Assessment): { label: string; tone: "neutral" | "info" | "good" | "warn" | "bad" } {
  if (assessment.final_decision) {
    return {
      label: DECISION_LABEL[assessment.final_decision] ?? assessment.final_decision,
      tone: DECISION_TONE[assessment.final_decision] ?? "neutral",
    };
  }
  if (assessment.submitted_at) return { label: "With data protection", tone: "info" };
  return { label: "Draft", tone: "neutral" };
}

/*
  A department lead's data protection assessments.

  Theirs and nobody else's. A team lead is not legal, and a list of every
  product in the organisation under assessment is not theirs to read; the API
  scopes it to what they raised.
*/
export default function PortalAssessments() {
  const router = useRouter();
  const mine = useApi<Assessment[]>("/assessments/mine");
  const [opening, setOpening] = React.useState(false);
  const [name, setName] = React.useState("");

  const start = useAction(async () => {
    const created = await api<Assessment>("/assessments/dpia", {
      method: "POST",
      body: { project_name: name.trim() },
    });
    router.push(`/portal/assessments/${created.id}`);
  });

  const rows = mine.data ?? [];

  return (
    <div className="space-y-6">
      <PageTitle
        title="Data protection assessments"
        subtitle={
          "Before a product handles personal data, the team building it describes what it " +
          "does with that data. The data protection officer reads it, scores it and decides."
        }
        actions={
          <Button variant="primary" onClick={() => setOpening(true)}>
            Start an assessment
          </Button>
        }
      />

      {mine.loading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <Empty
          title="You have not started an assessment"
          detail="Start one when your team is building something that will collect or process personal data."
        />
      ) : (
        <div className="space-y-3">
          {rows.map((assessment) => {
            const shown = state(assessment);
            return (
              <Card key={assessment.id}>
                <CardBody className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  <div className="min-w-0 flex-1">
                    <Link
                      href={`/portal/assessments/${assessment.id}`}
                      className="block truncate font-medium no-underline hover:underline"
                    >
                      {assessment.title}
                    </Link>
                    <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <Mono>{assessment.reference}</Mono>
                      {assessment.submitted_at ? (
                        <span>Submitted {formatDate(assessment.submitted_at)}</span>
                      ) : (
                        <span>Not yet submitted</span>
                      )}
                      {assessment.review_date ? (
                        <span>Review due {formatDate(assessment.review_date)}</span>
                      ) : null}
                    </div>
                  </div>
                  <Pill tone={shown.tone}>{shown.label}</Pill>
                  <Link href={`/portal/assessments/${assessment.id}`} className="no-underline">
                    <Button size="sm">
                      {assessment.submitted_at ? "Read it" : "Continue"}
                    </Button>
                  </Link>
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}

      <Card>
        <CardHeader
          title="When an assessment is needed"
          subtitle="If any of these describe what your team is building, start one before the build does."
        />
        <CardBody>
          <ul className="ml-5 list-disc space-y-1.5 text-sm leading-relaxed marker:text-muted-foreground">
            <li>It collects personal data from people, or receives it from somewhere that did.</li>
            <li>It profiles people, scores them, or makes a decision about them automatically.</li>
            <li>It handles health, biometric, financial or other sensitive data.</li>
            <li>It monitors behaviour or location systematically.</li>
            <li>It sends personal data outside Nigeria, including to a cloud region abroad.</li>
            <li>The people whose data it uses are children, patients, or otherwise vulnerable.</li>
          </ul>
        </CardBody>
      </Card>

      <Modal
        open={opening}
        title="Start a data protection assessment"
        subtitle="Name the thing being built. Everything else can be filled in over time, and is saved as you type."
        onClose={() => setOpening(false)}
        footer={
          <>
            <Button onClick={() => setOpening(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={name.trim().length < 3 || start.busy}
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
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="EqualyzAI Voice Agents"
          />
        </Field>
        <Notice tone="info" title="It does not have to be finished today">
          Thirteen sections, and several need somebody else on your team to answer. Everything is
          saved as you write it, and nothing reaches the data protection officer until you submit.
        </Notice>
      </Modal>
    </div>
  );
}
