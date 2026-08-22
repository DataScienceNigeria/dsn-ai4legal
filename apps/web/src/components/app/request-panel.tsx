"use client";

import * as React from "react";

import { Card, CardBody, CardHeader, KeyValue, Mono, Pill } from "@/components/ui";
import type { RequestDetail } from "@/lib/types";
import { formatDate, formatDateTime, formatMoney, titleCase } from "@/lib/utils";

const DECLARED: [keyof RequestDetail, string][] = [
  ["personal_data", "Personal data"],
  ["special_category_data", "Special-category data"],
  ["third_party_confidential", "Third-party confidential"],
  ["leaves_nigeria", "Leaves Nigeria"],
];

/*
  Label beside value, not above it. A stack of headings with one short answer
  under each reads as a form someone is still filling in; a list of statements
  reads as the request.
*/
function Detail({ label, children }: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <div className="grid gap-x-3 gap-y-0.5 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm">{children}</dd>
    </div>
  );
}

function Attachments({ request }: Readonly<{ request: RequestDetail }>) {
  if (!request.attachments.length) {
    return <span className="text-muted-foreground">Nothing was attached.</span>;
  }

  return (
    <ul className="space-y-1.5">
      {request.attachments.map((file) => (
        <li key={file.id} className="flex items-center gap-2">
          <Pill tone={file.scan_status === "clean" ? "good" : "warn"}>
            {titleCase(file.scan_status)}
          </Pill>
          <span className="min-w-0 truncate">{file.filename}</span>
          <span className="ml-auto shrink-0 text-xs text-muted-foreground">
            {Math.max(1, Math.round(file.size_bytes / 1024))} KB
          </span>
        </li>
      ))}
    </ul>
  );
}

function normalise(value: string | number | null): string {
  return String(value ?? "").trim().toLowerCase();
}

/*
  An answer that repeats something already on the page is dropped. The intake
  form writes the counterparty, the needed-by date, the value and the purpose
  into their own columns as well as into the answers, so rendering the answers
  verbatim showed each of them twice and invited the reader to check whether
  the two copies agreed.
*/
function extraAnswers(request: RequestDetail) {
  const shown = new Set(
    [
      request.purpose,
      request.proposed_counterparty,
      request.required_date,
      request.value_amount,
      request.subject,
    ]
      .map(normalise)
      .filter(Boolean),
  );
  return request.answers.filter((answer) => !shown.has(normalise(answer.value)));
}

/*
  The same request, read on two screens that already say different things about
  it. In triage nothing else on the page carries the facts, so the left column
  states them. On a matter the record card and the header have already said the
  organisation, the counterparty, the value and the title, and repeating them
  would make the reader check whether the two copies agree. `facts` is what
  that difference amounts to.

  Two columns, not one. The facts are short lines and the prose is long ones,
  and a single column made the short lines run the width of the display with
  the label and the value at opposite ends of it.
*/
export function RequestPanel({
  request,
  title,
  subtitle,
  facts = true,
}: Readonly<{
  request: RequestDetail;
  title?: string;
  subtitle?: string;
  facts?: boolean;
}>) {
  const flags = DECLARED.filter(([key]) => request[key]);

  const supplied = (
    <dl className="space-y-2.5">
      {request.purpose ? (
        <Detail label="Purpose, in their words">
          <span className="whitespace-pre-wrap leading-relaxed">{request.purpose}</span>
        </Detail>
      ) : null}

      {extraAnswers(request).map((answer) => (
        <Detail key={answer.name} label={answer.label}>
          <span className="whitespace-pre-wrap">{answer.value}</span>
        </Detail>
      ))}

      <Detail label="Declared data">
        {flags.length ? (
          <span className="flex flex-wrap gap-1.5">
            {flags.map(([key, label]) => (
              <Pill key={String(key)} tone="warn">
                {label}
              </Pill>
            ))}
          </span>
        ) : (
          <span className="text-muted-foreground">
            Nothing declared. The requester answered no to all four questions.
          </span>
        )}
      </Detail>

      <Detail label="Attachments">
        <Attachments request={request} />
      </Detail>
    </dl>
  );

  return (
    <Card>
      <CardHeader
        title={title ?? request.subject}
        subtitle={
          subtitle ??
          `${request.request_type}, raised by ${request.requester_name ?? "an unknown account"}`
        }
        actions={<Mono>{request.reference}</Mono>}
      />
      {facts ? (
        <CardBody className="grid gap-x-8 gap-y-5 lg:grid-cols-2">
          <KeyValue
            rows={[
              ["Organisation", request.entity],
              ["Raised", formatDateTime(request.submitted_at)],
              [
                "Needed by",
                request.required_date ? formatDate(request.required_date) : "Not stated",
              ],
              ["Counterparty", request.proposed_counterparty ?? "None named"],
              [
                "Value",
                request.value_amount === null
                  ? "Not stated"
                  : formatMoney(request.value_amount, request.value_currency),
              ],
              ["Requester", request.requester_email ?? "Unknown"],
            ]}
          />
          <div className="lg:border-l lg:pl-8">{supplied}</div>
        </CardBody>
      ) : (
        <CardBody className="grid gap-x-8 gap-y-5 lg:grid-cols-2">
          <KeyValue
            rows={[
              ["Raised", formatDateTime(request.submitted_at)],
              ["By", request.requester_email ?? request.requester_name ?? "Unknown"],
              [
                "They asked for it by",
                request.required_date ? formatDate(request.required_date) : "No date given",
              ],
            ]}
          />
          <div className="lg:border-l lg:pl-8">{supplied}</div>
        </CardBody>
      )}
    </Card>
  );
}
