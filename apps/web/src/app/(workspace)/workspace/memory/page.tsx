"use client";

import * as React from "react";

import { useSession } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  Input,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import type { Answer } from "@/lib/types";
import { titleCase } from "@/lib/utils";

const SUGGESTED = [
  "Have we ever accepted uncapped liability, and who approved it?",
  "What notice period do we normally accept on termination for convenience?",
  "What should I know about Sahel Cloud Services before I negotiate?",
  "Summarise the Anambra investigation matter for me.",
];

type Turn = { question: string; answer: Answer | null; pending: boolean };

export default function Memory() {
  const { entity } = useSession();
  const [question, setQuestion] = React.useState("");
  const [turns, setTurns] = React.useState<Turn[]>([]);

  const ask = useAction(async (text: string) => {
    setTurns((prev) => [...prev, { question: text, answer: null, pending: true }]);
    try {
      const answer = await api<Answer>("/ai/ask", { method: "POST", body: { question: text } });
      setTurns((prev) =>
        prev.map((turn, index) =>
          index === prev.length - 1 ? { ...turn, answer, pending: false } : turn,
        ),
      );
      return answer;
    } catch (exception) {
      setTurns((prev) => prev.slice(0, -1));
      throw exception;
    }
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    void ask.run(question.trim());
    setQuestion("");
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="Ask memory"
        subtitle={
          "Questions over the approved library, executed agreements, decision records and " +
          "playbooks. Any statement without a citation is suppressed rather than shown."
        }
        actions={
          turns.length ? (
            <Button size="sm" onClick={() => setTurns([])}>
              Clear
            </Button>
          ) : null
        }
      />

      {turns.length === 0 ? (
        <Card>
          <CardBody className="space-y-3">
            <div className="text-sm text-muted-foreground">
              This memory builds itself from normal work. Decision entries, accepted redlines,
              approved fallback usage and executed agreements are indexed on the events that
              create them, so there is no separate knowledge-entry task.
            </div>
            <div className="flex flex-wrap gap-2">
              {SUGGESTED.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => void ask.run(prompt)}
                  className="rounded-md border px-3 py-1.5 text-left text-sm hover:bg-muted"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </CardBody>
        </Card>
      ) : null}

      <div className="space-y-4">
        {turns.map((turn, index) => (
          <div key={`${turn.question}-${index}`} className="space-y-3">
            <div className="flex justify-end">
              <div className="max-w-[70%] rounded-lg bg-secondary px-3.5 py-2 text-sm text-secondary-foreground">
                {turn.question}
              </div>
            </div>

            {turn.pending ? (
              <Spinner label="Retrieving under your permissions" />
            ) : turn.answer?.refused ? (
              <Refusal title="I cannot answer that" reason={turn.answer.refusal_reason} />
            ) : turn.answer ? (
              <Card>
                <CardBody className="space-y-3">
                  {turn.answer.paragraphs.map((paragraph, paragraphIndex) => (
                    <p key={paragraphIndex} className="text-sm leading-relaxed">
                      {paragraph.text}{" "}
                      {paragraph.cites.map((cite) => (
                        <Pill key={cite} tone="info" className="ml-1 align-middle">
                          {cite}
                        </Pill>
                      ))}
                    </p>
                  ))}

                  {turn.answer.suppressed_statements > 0 ? (
                    <Notice tone="warn" title="Some statements were suppressed">
                      {turn.answer.suppressed_statements} statement
                      {turn.answer.suppressed_statements === 1 ? " was" : "s were"} left out
                      because no retrieved record supported them.
                    </Notice>
                  ) : null}

                  {turn.answer.note ? (
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      {turn.answer.note}
                    </p>
                  ) : null}

                  {turn.answer.sources.length ? (
                    <div className="border-t pt-3">
                      <div className="mb-2 text-xs font-semibold text-muted-foreground">
                        SOURCES
                      </div>
                      <div className="space-y-1.5">
                        {turn.answer.sources.map((source) => (
                          <div key={source.reference} className="flex items-baseline gap-2 text-sm">
                            <Mono>{source.reference}</Mono>
                            <span className="text-muted-foreground">
                              {titleCase(source.kind)}
                              {source.detail ? `, ${source.detail}` : ""}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </CardBody>
              </Card>
            ) : null}
          </div>
        ))}
      </div>

      {ask.error ? <Refusal title="The question could not be answered" reason={ask.error.message} /> : null}

      <form onSubmit={submit} className="flex gap-2">
        <Input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={`Ask about ${entity} positions, agreements or decisions`}
          className="flex-1"
        />
        <Button type="submit" variant="primary" disabled={ask.busy || !question.trim()}>
          Ask
        </Button>
      </form>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Retrieval filters by entity, role and matter access before ranking rather than after, so a
        record you cannot open never enters the candidate set. No title, snippet or citation can
        leak from it.
      </p>
    </div>
  );
}
