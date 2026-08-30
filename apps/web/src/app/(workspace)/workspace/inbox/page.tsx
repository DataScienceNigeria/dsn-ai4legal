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
import { api, view as openFile } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Communication, ExtractedValue } from "@/lib/types";
import { cn, formatDateTime, titleCase } from "@/lib/utils";

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
            <Button variant="primary" disabled={correct.busy} onClick={() => void correct.run()}>
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
                disabled={decide.busy}
                onClick={() => void decide.run("confirmed")}
              >
                Confirm
              </Button>
              <Button size="sm" disabled={decide.busy} onClick={() => setCorrecting(true)}>
                Correct
              </Button>
              <Button size="sm" disabled={decide.busy} onClick={() => void decide.run("rejected")}>
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
              disabled={decide.busy}
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

export default function Inbox() {
  const { entity } = useSession();
  const [view, setView] = React.useState("all");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const messages = useApi<Communication[]>(`/ai/inbox?view=${view}`, [entity, view]);
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

  const confirm = useAction(async (message: Communication) => {
    await api(`/ai/inbox/${message.id}/confirm`, {
      method: "POST",
      body: {
        request_type_code: message.proposed_matter_type ?? "something_else",
        entity: message.entity,
        priority: message.proposed_priority ?? "normal",
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

      {error ? <Refusal title="That action was refused" reason={error.message} /> : null}

      <div className="grid gap-4 lg:gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Card>
          <CardHeader title={`${messages.data?.length ?? 0} messages`} />
          <div className="max-h-[620px] overflow-y-auto">
            {messages.loading ? (
              <Spinner />
            ) : !messages.data?.length ? (
              <Empty title="Nothing in this view" />
            ) : (
              messages.data.map((message) => (
                <button
                  key={message.id}
                  onClick={() => setSelectedId(message.id)}
                  className={cn(
                    "block w-full border-b p-4 text-left last:border-b-0 hover:bg-muted/60",
                    current?.id === message.id && "bg-brand/5 shadow-[inset_2px_0_0] shadow-brand",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-xs text-muted-foreground">{message.sender}</span>
                    <span className="shrink-0 text-2xs text-muted-foreground">
                      {message.age_days}d
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-sm font-medium">{message.subject}</div>
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
                    <Button size="sm" disabled={busy} onClick={() => void classify.run(current.id)}>
                      Classify
                    </Button>
                    <Button size="sm" disabled={busy} onClick={() => void extract.run(current.id)}>
                      Extract facts
                    </Button>
                    <CorrectClassification message={current} onDone={() => messages.reload()} />
                  </>
                }
              />
              <CardBody className="space-y-3">
                <p className="whitespace-pre-wrap rounded-md border bg-muted/40 p-3 text-sm leading-relaxed">
                  {current.body}
                </p>

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
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="primary"
                  disabled={busy}
                  onClick={() => void confirm.run(current)}
                >
                  Create a matter from this
                </Button>
                <span className="text-xs text-muted-foreground">
                  No matter exists, and nothing has been sent, until you confirm here.
                </span>
              </div>
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
