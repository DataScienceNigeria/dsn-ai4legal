"use client";

import * as React from "react";

import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Empty,
  Field,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { ConsultantReview } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const STATUS_TONE: Record<string, "warn" | "info" | "good"> = {
  requested: "warn",
  returned: "info",
  assessed: "good",
};

const STATUS_LABEL: Record<string, string> = {
  requested: "Waiting on you",
  returned: "With the legal team",
  assessed: "Closed",
};

/*
  Comments, not changes.

  The draft is not theirs to edit. A review that could rewrite the document
  would put wording into an agreement that no clause owner ever cleared, which
  is the same rule the platform applies to its own model layer, applied to a
  person who is not on the staff.
*/
function Respond({
  review,
  onSent,
}: Readonly<{ review: ConsultantReview; onSent: () => void }>) {
  const [comments, setComments] = React.useState("");

  const send = useAction(async () => {
    await api(`/consultant-reviews/${review.id}/comments`, {
      method: "POST",
      body: { comments: comments.trim() },
    });
    setComments("");
    onSent();
  });

  return (
    <div className="space-y-3 border-t pt-4">
      {send.error ? (
        <Refusal
          title="That was not sent"
          reason={send.error.message}
          reasons={send.error.reasons}
        />
      ) : null}
      <Field
        label="Your comments"
        required
        hint="The legal team reads this and decides what to incorporate. Nothing here changes the document."
      >
        <Textarea
          value={comments}
          onChange={(event) => setComments(event.target.value)}
          className="min-h-[8rem] leading-relaxed"
        />
      </Field>
      <Button
        variant="primary"
        disabled={comments.trim().length < 25 || send.busy}
        onClick={() => void send.run()}
      >
        Send to the legal team
      </Button>
    </div>
  );
}

export default function ConsultantReviews() {
  const reviews = useApi<ConsultantReview[]>("/consultant-reviews/mine");
  const rows = reviews.data ?? [];
  const waiting = rows.filter((row) => row.status === "requested").length;

  if (reviews.loading) return <Spinner />;
  if (reviews.error) {
    return <Refusal title="That is not available to you" reason={reviews.error.message} />;
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="What you have been asked to read"
        subtitle={
          waiting > 0
            ? `${waiting} waiting on you.`
            : "Nothing is waiting on you at the moment."
        }
      />

      <Notice tone="info" title="What you can see">
        Only the matters you have been asked about. Access is granted one matter at a time when
        the legal team sends you something, so nothing else in the organisation is visible here.
      </Notice>

      {rows.length === 0 ? (
        <Empty
          title="Nothing has been sent to you"
          detail="A review appears here when the legal team asks you to look at a draft."
        />
      ) : (
        rows.map((review) => (
          <Card key={review.id}>
            <CardHeader
              title={review.matter_title ?? "A draft"}
              subtitle={
                <span className="flex flex-wrap items-center gap-2">
                  <Mono>{review.matter_number}</Mono>
                  {review.document_name ? <span>{review.document_name}</span> : null}
                  {review.due_date ? <span>Wanted by {formatDate(review.due_date)}</span> : null}
                </span>
              }
              actions={
                <Pill tone={STATUS_TONE[review.status] ?? "neutral"}>
                  {STATUS_LABEL[review.status] ?? review.status}
                </Pill>
              }
            />
            <CardBody className="space-y-4">
              <div>
                <div className="text-xs text-muted-foreground">What they want you to look at</div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{review.brief}</p>
              </div>

              {review.comments ? (
                <div>
                  <div className="text-xs text-muted-foreground">
                    {`What you said, ${formatDate(review.returned_at)}`}
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{review.comments}</p>
                </div>
              ) : null}

              {review.assessment ? (
                <Notice tone="good" title="What the legal team did with it">
                  {review.assessment}
                </Notice>
              ) : null}

              {review.status === "requested" ? (
                <Respond review={review} onSent={reviews.reload} />
              ) : null}
            </CardBody>
          </Card>
        ))
      )}
    </div>
  );
}
