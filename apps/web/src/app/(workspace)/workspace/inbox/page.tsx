"use client";

import * as React from "react";

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
  Select,
  Spinner,
  Tabs,
  Textarea,
} from "@/components/ui";
import { ApiError, api, view as openFile } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Communication, ExtractedValue, RequestType } from "@/lib/types";
import { cn, formatDateTime, titleCase } from "@/lib/utils";

/* The mailbox's own state, as the connector last saw it. Separate from the
   Legal tabs above it on purpose: read means somebody opened it in the
   mailbox, handled means Legal has dealt with it, and neither implies the
   other. */
const MAILBOX_STATES = [
  { id: "all", label: "All mail" },
  { id: "unread", label: "Unread" },
  { id: "read", label: "Read" },
  { id: "starred", label: "Starred" },
  { id: "important", label: "Important" },
  { id: "sent", label: "Sent" },
];

const CLASSIFICATIONS = [
  "action_required",
  "deadline_present",
  "awareness_only",
  "possible_contract",
  "privacy_issue",
  "vendor_issue",
  "unclear",
];

/*
  A wrong classification is only useful if someone can say so. The correction
  is what the accuracy report counts and what the golden set later draws on.
*/
function CorrectClassification({
  message,
  onDone,
}: Readonly<{ message: Communication; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [classification, setClassification] = React.useState(
    message.classification ?? "action_required",
  );
  const [reason, setReason] = React.useState("");

  const correct = useAction(async () => {
    await api(`/ai/inbox/${message.id}/correct`, {
      method: "POST",
      body: { classification, reason: reason || undefined },
    });
    onDone();
    setOpen(false);
  });

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Correct
      </Button>
      <Modal
        open={open}
        title="Correct this classification"
        subtitle="The correction is recorded against the interaction and becomes a candidate for the evaluation set."
        width="sm"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={correct.busy} loading={correct.busy} onClick={() => void correct.run()}>
              Record the correction
            </Button>
          </>
        }
      >
        <Field label="What it should have been" required>
          <Select
            value={classification}
            onChange={(event) => setClassification(event.target.value)}
          >
            {CLASSIFICATIONS.map((value) => (
              <option key={value} value={value}>
                {titleCase(value)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Why" hint="Optional, and worth writing when the reason is not obvious.">
          <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
        {correct.error ? (
          <Refusal title="That correction was refused" reason={correct.error.message} />
        ) : null}
      </Modal>
    </>
  );
}

function ExtractedValueRow({
  value,
  onDone,
}: Readonly<{ value: ExtractedValue; onDone: () => void }>) {
  const [correcting, setCorrecting] = React.useState(false);
  const [corrected, setCorrected] = React.useState(value.value);

  const decide = useAction(async (decision: string, correctedValue?: string) => {
    await api(`/ai/extracted/${value.id}/decision`, {
      method: "POST",
      body: { decision, corrected_value: correctedValue },
    });
    onDone();
    setCorrecting(false);
  });

  return (
    <div className="border-b p-4 last:border-b-0">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <span className="text-xs text-muted-foreground">{titleCase(value.field_name)}</span>
          <div className="text-sm font-medium">{value.corrected_value ?? value.value}</div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {value.decision === "pending" ? (
            <>
              <Button
                size="sm"
                variant="primary"
                disabled={decide.busy} loading={decide.busy}
                onClick={() => void decide.run("confirmed")}
              >
                Confirm
              </Button>
              <Button size="sm" disabled={decide.busy} loading={decide.busy} onClick={() => setCorrecting(true)}>
                Correct
              </Button>
              <Button size="sm" disabled={decide.busy} loading={decide.busy} onClick={() => void decide.run("rejected")}>
                Reject
              </Button>
            </>
          ) : (
            <Pill tone={value.decision === "confirmed" ? "good" : "neutral"}>
              {titleCase(value.decision)}
            </Pill>
          )}
        </div>
      </div>
      <p className="mt-1.5 text-xs italic leading-relaxed text-muted-foreground">
        &ldquo;{value.source_sentence}&rdquo;
      </p>
      {decide.error ? (
        <p className="mt-1.5 text-xs text-destructive">{decide.error.message}</p>
      ) : null}
      <Modal
        open={correcting}
        title={`Correct ${titleCase(value.field_name)}`}
        subtitle="The corrected value is what the record keeps, and the original stays visible on the interaction."
        width="sm"
        onClose={() => setCorrecting(false)}
        footer={
          <>
            <Button onClick={() => setCorrecting(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={decide.busy} loading={decide.busy}
              onClick={() => void decide.run("corrected", corrected)}
            >
              Save the correction
            </Button>
          </>
        }
      >
        <Field label="Correct value" required>
          <Input value={corrected} onChange={(event) => setCorrected(event.target.value)} />
        </Field>
      </Modal>
    </div>
  );
}

/*
  Mail text with its links folded. A tracking link runs to four hundred
  characters and, printed in full, took the whole message. Each is shown as
  its host and the start of its path, opens in a new tab with no referrer, and
  keeps the full address on hover so nothing about where it goes is hidden.
*/
const LINK = /https?:\/\/[^\s<>"')\]]+/g;

function shortLink(url: string): string {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, "");
    const path = parsed.pathname === "/" ? "" : parsed.pathname;
    const label = host + path;
    return label.length > 40 ? `${label.slice(0, 40)}…` : label;
  } catch {
    return url.length > 40 ? `${url.slice(0, 40)}…` : url;
  }
}

function MailText({ text }: Readonly<{ text: string }>) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(LINK)) {
    const start = match.index ?? 0;
    if (start > last) parts.push(text.slice(last, start));
    parts.push(
      <a
        key={start}
        href={match[0]}
        title={match[0]}
        target="_blank"
        rel="noopener noreferrer nofollow"
        className="text-brand underline decoration-dotted underline-offset-2"
      >
        {shortLink(match[0])}
      </a>,
    );
    last = start + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

export default function Inbox() {
  const { entity } = useSession();
  const [view, setView] = React.useState("all");
  const [state, setState] = React.useState("all");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [showQuoted, setShowQuoted] = React.useState(false);

  const messages = useApi<Communication[]>(`/ai/inbox?view=${view}&state=${state}`, [
    entity,
    view,
    state,
  ]);
  const current =
    messages.data?.find((message) => message.id === selectedId) ?? messages.data?.[0] ?? null;

  // Fetched rather than linked: the file is behind the same bearer token as
  // everything else, so an href would open a 401 in a new tab.
  const open = useAction(async (path: string) => {
    await openFile(path);
  });

  const classify = useAction(async (id: string) => {
    await api(`/ai/classify/${id}`, { method: "POST" });
    messages.reload();
  });

  const extract = useAction(async (id: string) => {
    await api(`/ai/extract/${id}`, { method: "POST" });
    messages.reload();
  });

  /*
    What the matter will be opened as, shown and changeable before it is
    created. The model proposes the type as free text, so it is matched to a
    real request type here; one it cannot be matched to starts on "something
    else" instead of failing at the moment of confirming.
  */
  const requestTypes = useApi<RequestType[]>("/requests/types");
  const [matterType, setMatterType] = React.useState("");
  const [matterPriority, setMatterPriority] = React.useState("normal");

  const proposedTypeCode = React.useMemo(() => {
    const types = requestTypes.data ?? [];
    const proposal = current?.proposed_matter_type?.trim().toLowerCase();
    if (!proposal) return null;
    const match = types.find(
      (type) =>
        type.code.toLowerCase() === proposal ||
        type.business_label.toLowerCase() === proposal ||
        type.agreement_type.toLowerCase() === proposal,
    );
    return match?.code ?? null;
  }, [requestTypes.data, current?.proposed_matter_type]);

  React.useEffect(() => {
    const types = requestTypes.data ?? [];
    const fallback =
      types.find((type) => type.code === "something_else")?.code ?? types[0]?.code ?? "";
    setMatterType(proposedTypeCode ?? fallback);
    setMatterPriority(current?.proposed_priority ?? "normal");
  }, [current?.id, current?.proposed_priority, proposedTypeCode, requestTypes.data]);

  const confirm = useAction(async (message: Communication) => {
    await api(`/ai/inbox/${message.id}/confirm`, {
      method: "POST",
      body: {
        request_type_code: matterType,
        entity: message.entity,
        priority: matterPriority,
        send_acknowledgment: false,
      },
    });
    messages.reload();
  });

  const busy = classify.busy || extract.busy || confirm.busy;
  const error = classify.error ?? extract.error ?? confirm.error;

  return (
    <div className="space-y-6">
      <PageTitle
        title="Inbox intelligence"
        subtitle={
          "The platform reads the approved mailbox, classifies what arrives and proposes a " +
          "next step. It never speaks for Legal, and nothing is sent without a person."
        }
      />

      <Tabs
        tabs={[
          { id: "all", label: "All" },
          { id: "action", label: "Action queue" },
          { id: "watch", label: "Implied work" },
          { id: "handled", label: "Handled" },
        ]}
        active={view}
        onChange={(id) => {
          setView(id);
          setSelectedId(null);
        }}
      />

      {view === "watch" ? (
        <Notice tone="warn" title="Work implied but not assigned">
          These messages describe legal work that nobody has asked for yet. They sit here with an
          ageing clock, separate from the action queue, because this is where work is usually lost.
        </Notice>
      ) : null}

      <div className="grid gap-4 lg:gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Card>
          <CardHeader
            title={`${messages.data?.length ?? 0} messages`}
            actions={
              <Select
                aria-label="Mailbox status"
                value={state}
                onChange={(event) => {
                  setState(event.target.value);
                  setSelectedId(null);
                }}
                className="h-8 w-36 text-xs"
              >
                {MAILBOX_STATES.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </Select>
            }
          />
          <div className="max-h-[620px] overflow-y-auto">
            {messages.loading ? (
              <Spinner />
            ) : !messages.data?.length ? (
              <Empty title="Nothing in this view" />
            ) : (
              messages.data.map((message) => (
                <button
                  key={message.id}
                  onClick={() => {
                    setSelectedId(message.id);
                    setShowQuoted(false);
                  }}
                  className={cn(
                    "block w-full border-b p-4 text-left last:border-b-0 hover:bg-muted/60",
                    current?.id === message.id && "bg-brand/5 shadow-[inset_2px_0_0] shadow-brand",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1.5 truncate text-xs text-muted-foreground">
                      {message.mailbox_read === false ? (
                        <span
                          aria-label="Unread in the mailbox"
                          className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand"
                        />
                      ) : null}
                      <span className="truncate">
                        {message.direction === "outbound" ? "To " : ""}
                        {message.direction === "outbound"
                          ? (message.participants?.[0]?.address ?? message.sender)
                          : message.sender}
                      </span>
                    </span>
                    <span className="shrink-0 text-2xs text-muted-foreground">
                      {message.age_days}d
                    </span>
                  </div>
                  <div
                    className={cn(
                      "mt-0.5 truncate text-sm",
                      message.mailbox_read === false ? "font-semibold" : "font-medium",
                    )}
                  >
                    {message.subject}
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {message.classification ? (
                      <Pill tone={message.classification === "action_required" ? "warn" : "neutral"}>
                        {titleCase(message.classification)}
                      </Pill>
                    ) : (
                      <Pill tone="neutral">Not classified</Pill>
                    )}
                    {message.classification_confidence ? (
                      <Mono>{Math.round(message.classification_confidence * 100)}% confidence</Mono>
                    ) : null}
                    {message.quarantined ? <Pill tone="bad">Quarantined</Pill> : null}
                    {message.direction === "outbound" ? <Pill tone="info">Sent</Pill> : null}
                    {message.mailbox_labels.includes("STARRED") ? (
                      <Pill tone="warn">Starred</Pill>
                    ) : null}
                    {message.mailbox_labels.includes("IMPORTANT") ? (
                      <Pill tone="neutral">Important</Pill>
                    ) : null}
                    {message.attachments.length ? (
                      <Mono>
                        {message.attachments.length} file{message.attachments.length === 1 ? "" : "s"}
                      </Mono>
                    ) : null}
                  </div>
                </button>
              ))
            )}
          </div>
        </Card>

        {current ? (
          <div className="space-y-4">
            <Card>
              <CardHeader
                title={current.subject}
                subtitle={`${current.sender}, received ${formatDateTime(current.received_at)}`}
                actions={
                  <>
                    <Button
                      size="sm"
                      disabled={busy}
                      loading={classify.busy}
                      onClick={() => void classify.run(current.id)}
                    >
                      {classify.busy ? "Classifying" : "Classify"}
                    </Button>
                    <Button
                      size="sm"
                      disabled={busy}
                      loading={extract.busy}
                      onClick={() => void extract.run(current.id)}
                    >
                      {extract.busy ? "Extracting" : "Extract facts"}
                    </Button>
                    <CorrectClassification message={current} onDone={() => messages.reload()} />
                  </>
                }
              />
              <CardBody className="space-y-3">
                {/* Beside the buttons that caused it. Above the list it sat out
                    of sight, and a refused Classify read as one that did nothing. */}
                {error ? (
                  <Refusal
                    title="That did not run"
                    reason={error.message}
                    reasons={error instanceof ApiError ? error.reasons : undefined}
                  />
                ) : null}
                <p className="whitespace-pre-wrap rounded-md border bg-muted/40 p-3 text-sm leading-relaxed [overflow-wrap:anywhere]">
                  <MailText text={current.body} />
                </p>

                {/*
                  The history quoted under a reply. Folded by default, because
                  shown whole it buried a two-line answer under a screen of
                  chevrons, and kept one click away, because the thread is
                  often where the commitment was actually made.
                */}
                {current.body_quoted ? (
                  <div className="rounded-md border">
                    <button
                      onClick={() => setShowQuoted((open) => !open)}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-xs text-muted-foreground hover:bg-muted/60"
                    >
                      <span>Earlier in the thread</span>
                      <span aria-hidden>{showQuoted ? "Hide" : "Show"}</span>
                    </button>
                    {showQuoted ? (
                      <p className="whitespace-pre-wrap border-t p-3 text-xs leading-relaxed text-muted-foreground [overflow-wrap:anywhere]">
                        <MailText text={current.body_quoted} />
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {/*
                  What arrived with the message. The agreement is usually the
                  attachment rather than the email, so a message that showed its
                  body and nothing else was showing the covering note and hiding
                  the thing it covered. Each file opens in place; every read is
                  audited against the message it came in on.
                */}
                {current.attachments.length ? (
                  <div className="space-y-1.5">
                    <div className="text-xs font-medium text-muted-foreground">
                      {current.attachments.length === 1
                        ? "One file arrived with this message"
                        : `${current.attachments.length} files arrived with this message`}
                    </div>
                    {current.attachments.map((file) => (
                      <button
                        key={file.id}
                        type="button"
                        className="flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left text-sm hover:bg-muted/40"
                        onClick={() =>
                          void open.run(
                            `/ai/inbox/${current.id}/attachments/${file.id}`,
                          )
                        }
                      >
                        <span className="min-w-0 flex-1 truncate">{file.filename}</span>
                        {file.scan_status === "clean" ? null : (
                          <Pill tone="bad">{titleCase(file.scan_status)}</Pill>
                        )}
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {Math.max(1, Math.round(file.size_bytes / 1024))} KB
                        </span>
                      </button>
                    ))}
                    {open.error ? (
                      <Refusal title="That file could not be opened" reason={open.error.message} />
                    ) : null}
                  </div>
                ) : null}
              </CardBody>
            </Card>

            {current.injection_flagged ? (
              <Refusal
                title="Instruction-like content was found in this message"
                reason={
                  "It has been treated as data, not as an instruction, and the message is " +
                  "quarantined pending review. Legal and IT security have a record of it."
                }
              />
            ) : null}

            {current.implied_work ? (
              <Notice tone="warn" title="This implies future legal work">
                <span className="italic">&ldquo;{current.implied_work_phrase}&rdquo;</span>
              </Notice>
            ) : null}

            {current.extracted_values.length ? (
              <Card>
                <CardHeader
                  title="Extracted facts"
                  subtitle="Each is a suggestion until confirmed, and each shows the sentence it came from."
                />
                <div>
                  {current.extracted_values.map((value) => (
                    <ExtractedValueRow
                      key={value.id}
                      value={value}
                      onDone={() => messages.reload()}
                    />
                  ))}
                </div>
              </Card>
            ) : null}

            {current.proposed_acknowledgment ? (
              <Card>
                <CardHeader
                  title="Proposed acknowledgment"
                  subtitle="Administrative only. It carries no legal position, advice or commitment."
                  actions={<Pill tone="novel">Draft, not sent</Pill>}
                />
                <CardBody>
                  <p className="whitespace-pre-wrap rounded-md border p-3 text-sm leading-relaxed">
                    {current.proposed_acknowledgment}
                  </p>
                </CardBody>
              </Card>
            ) : null}

            {!current.handled ? (
              <Card>
                <CardHeader
                  title="Open a matter"
                  subtitle={
                    current.classification
                      ? "Proposed from the classification. Change either before creating."
                      : "Not classified yet. Classify for a proposal, or choose here."
                  }
                />
                <CardBody className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field
                      label="Request type"
                      hint={
                        current.proposed_matter_type && !proposedTypeCode
                          ? `Proposed "${current.proposed_matter_type}", which is not a request type here.`
                          : proposedTypeCode
                            ? "As proposed."
                            : undefined
                      }
                    >
                      <Select
                        value={matterType}
                        onChange={(event) => setMatterType(event.target.value)}
                      >
                        {(requestTypes.data ?? []).map((type) => (
                          <option key={type.code} value={type.code}>
                            {type.business_label}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field
                      label="Priority"
                      hint={current.proposed_priority ? "As proposed." : undefined}
                    >
                      <Select
                        value={matterPriority}
                        onChange={(event) => setMatterPriority(event.target.value)}
                      >
                        {["low", "normal", "high", "urgent"].map((value) => (
                          <option key={value} value={value}>
                            {titleCase(value)}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="primary"
                      disabled={busy || !matterType}
                      loading={confirm.busy}
                      onClick={() => void confirm.run(current)}
                    >
                      Create a matter from this
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      No matter exists, and nothing has been sent, until you confirm here.
                    </span>
                  </div>
                </CardBody>
              </Card>
            ) : (
              <Notice tone="good" title="Handled">
                A matter was created from this correspondence.
              </Notice>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
