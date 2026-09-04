"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import {
  EvidenceField,
  type Evidence,
} from "@/components/app/evidence-field";
import { useRoles } from "@/components/app/session";
import { StepUpGate } from "@/components/app/step-up";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
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
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Closure, ClosureItem } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

const STATUS_TONE: Record<string, "good" | "warn" | "neutral"> = {
  confirmed: "good",
  outstanding: "warn",
  not_applicable: "neutral",
};

const STATUS_LABEL: Record<string, string> = {
  confirmed: "Confirmed",
  outstanding: "Outstanding",
  not_applicable: "Does not apply",
};

/*
  Confirming one line of the checklist.

  Evidence is required where the line was defined to need it, and the refusal
  behind that is the whole point: the checklist exists so it can be shown to
  somebody afterwards, and an assurance with nothing behind it cannot be.
*/
function Confirm({
  item,
  contractId,
  onSaved,
}: Readonly<{
  item: ClosureItem;
  contractId: string;
  onSaved: (closure: Closure) => void;
}>) {
  const [open, setOpen] = React.useState(false);
  const [status, setStatus] = React.useState(
    item.status === "outstanding" ? "confirmed" : item.status,
  );
  const [evidence, setEvidence] = React.useState<Evidence>({
    documentId: item.evidence_document_id ?? null,
    reference: item.evidence_reference ?? "",
  });
  const [note, setNote] = React.useState(item.note ?? "");

  const save = useAction(async () => {
    const closure = await api<Closure>(`/closure-items/${item.id}`, {
      method: "POST",
      body: {
        status,
        evidence_reference: evidence.reference.trim() || null,
        evidence_document_id: evidence.documentId,
        note: note.trim() || null,
      },
    });
    setOpen(false);
    onSaved(closure);
  });

  // Evidence is asked for, not demanded. The field took any string at all, so
  // refusing without it stopped nothing except an honest confirmation whose
  // paper lives in another system.
  const ready = status !== "not_applicable" || note.trim().length > 0;

  return (
    <>
      <Button
        size="sm"
        variant={item.status === "outstanding" ? "primary" : "ghost"}
        onClick={() => setOpen(true)}
      >
        {item.status === "outstanding" ? "Confirm" : "Revise"}
      </Button>
      <Modal
        open={open}
        title={item.label}
        subtitle={item.intent}
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={!ready || save.busy} onClick={() => void save.run()}>
              Record it
            </Button>
          </>
        }
      >
        {save.error ? (
          <Refusal
            title="That was not recorded"
            reason={save.error.message}
            reasons={save.error.reasons}
          />
        ) : null}

        <Field label="Where it stands" required>
          <Select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="confirmed">Confirmed</option>
            <option value="outstanding">Still outstanding</option>
            {item.may_not_apply ? (
              <option value="not_applicable">Does not apply to this agreement</option>
            ) : null}
          </Select>
        </Field>

        {status === "confirmed" ? (
          <EvidenceField
            contractId={contractId}
            value={evidence}
            onChange={setEvidence}
            hint={
              item.evidence_required
                ? "The certificate, receipt, ticket or email that proves it. Attach it, or say where it is."
                : "Optional on this line. Attach a file or say where the proof is."
            }
          />
        ) : null}

        <Field
          label={status === "not_applicable" ? "Why it does not apply" : "Note"}
          required={status === "not_applicable"}
          hint={
            status === "not_applicable"
              ? "A line dismissed without a reason is a line nobody read."
              : "What was done, if it needs saying."
          }
        >
          <Textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            className="min-h-[4rem] leading-relaxed"
          />
        </Field>
      </Modal>
    </>
  );
}

function Close({
  closure,
  onClosed,
}: Readonly<{ closure: Closure; onClosed: (next: Closure) => void }>) {
  const [open, setOpen] = React.useState(false);
  const [status, setStatus] = React.useState("closed");
  const [note, setNote] = React.useState("");

  const close = useAction(async () => {
    const next = await api<Closure>(`/contracts/${closure.contract_id}/close`, {
      method: "POST",
      body: { status, note: note.trim() || null },
    });
    setOpen(false);
    onClosed(next);
  });

  const blocked = closure.blocking.length > 0;

  return (
    <>
      <Button variant="primary" disabled={blocked} onClick={() => setOpen(true)}>
        {blocked ? "Not ready to close" : "Close the agreement"}
      </Button>
      <Modal
        open={open}
        title="Close this agreement"
        subtitle={`${closure.contract_reference}. The checklist becomes the record of how it closed and does not change afterwards.`}
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={close.busy} onClick={() => void close.run()}>
              Close it
            </Button>
          </>
        }
      >
        {close.error ? (
          <Refusal
            title="It was not closed"
            reason={close.error.message}
            reasons={close.error.reasons}
          />
        ) : null}

        <Field label="How it ended" required>
          <Select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="closed">Ran to its end</option>
            <option value="terminated">Terminated early</option>
            <option value="lapsed">Allowed to lapse</option>
          </Select>
        </Field>

        <Field label="Anything worth recording">
          <Textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            className="min-h-[4rem] leading-relaxed"
          />
        </Field>
      </Modal>
      <StepUpGate action="Closing an agreement" state={close} />
    </>
  );
}

export default function ContractClosure() {
  const params = useParams<{ contractId: string }>();
  const id = params.contractId;
  const { has } = useRoles();
  const canAct = has("counsel", "head_of_legal", "admin");

  const closure = useApi<Closure>(`/contracts/${id}/closure`, [id]);
  const [data, setData] = React.useState<Closure | null>(null);

  React.useEffect(() => {
    if (closure.data) setData(closure.data);
  }, [closure.data]);

  const start = useAction(async () => {
    const next = await api<Closure>(`/contracts/${id}/closure`, { method: "POST" });
    setData(next);
  });

  if (closure.loading && !data) return <Spinner />;
  const current = data;

  const notOpened = !current || current.total === 0;

  return (
    <div className="space-y-5">
      <PageTitle
        title="Closing the agreement"
        subtitle={
          "What has to be true before an agreement is finished. Every line is confirmed by a " +
          "named person with the evidence, and the agreement does not close while one is open."
        }
        actions={
          <Link href={`/workspace/agreements/${id}/obligations`} className="no-underline">
            <Button size="sm">Its obligations</Button>
          </Link>
        }
      />

      {current ? (
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <Mono>{current.contract_reference}</Mono>
          {current.total > 0 ? (
            <span>{`${current.settled} of ${current.total} lines settled`}</span>
          ) : null}
          {current.opened_at ? <span>Opened {formatDate(current.opened_at)}</span> : null}
          {current.closed_at ? <span>Closed {formatDate(current.closed_at)}</span> : null}
        </div>
      ) : null}

      {start.error ? (
        <Refusal title="Closure was not opened" reason={start.error.message} />
      ) : null}

      {notOpened ? (
        <Card>
          <CardHeader
            title="Closure has not been opened"
            subtitle="Fourteen lines over five groups: deliverables, payment, property and access, data, and what survives the term."
          />
          <CardBody className="space-y-4">
            <Notice tone="info" title="The one that matters most">
              Personal data has to be returned or deleted and the deletion certified. The Act
              requires it, the agreement will have said so, and it is the line most often skipped
              because nobody is chasing it.
            </Notice>
            {canAct ? (
              <Button variant="primary" disabled={start.busy} onClick={() => void start.run()}>
                Open closure
              </Button>
            ) : (
              <p className="text-sm text-muted-foreground">Legal opens closure.</p>
            )}
          </CardBody>
        </Card>
      ) : (
        <>
          {current.closed_at ? (
            <Notice tone="good" title="This agreement is closed">
              {current.closure_note ?? "The checklist below is the record of how it closed."}
            </Notice>
          ) : current.blocking.length > 0 ? (
            <Notice
              tone="warn"
              title={`${current.blocking.length} thing${current.blocking.length === 1 ? "" : "s"} between this and closed`}
            >
              <ul className="ml-4 mt-1 list-disc space-y-1">
                {current.blocking.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </Notice>
          ) : (
            <Notice tone="good" title="Everything the checklist required is settled">
              The agreement can be closed.
            </Notice>
          )}

          {current.groups.map((group) => (
            <Card key={group.key}>
              <CardHeader
                title={group.title}
                subtitle={group.intent}
                actions={
                  <Pill
                    tone={
                      group.items.every((item) => item.status !== "outstanding")
                        ? "good"
                        : "warn"
                    }
                  >
                    {`${group.items.filter((item) => item.status !== "outstanding").length} of ${group.items.length}`}
                  </Pill>
                }
              />
              <div>
                {group.items.map((item) => (
                  <div
                    key={item.id}
                    className="flex flex-wrap items-start gap-3 border-b px-4 py-3 last:border-b-0 sm:px-5"
                  >
                    <div className="min-w-0 flex-1">
                      <div
                        className={cn(
                          "text-sm font-medium leading-snug",
                          item.status === "not_applicable" && "text-muted-foreground",
                        )}
                      >
                        {item.label}
                      </div>
                      <div className="mt-0.5 text-xs leading-snug text-muted-foreground">
                        {item.intent}
                      </div>
                      {item.evidence_reference ? (
                        <div className="mt-1 text-xs">{item.evidence_reference}</div>
                      ) : null}
                      {item.note ? (
                        <div className="mt-1 text-xs italic text-muted-foreground">{item.note}</div>
                      ) : null}
                      {item.confirmed_by_name ? (
                        <div className="mt-1 text-xs text-muted-foreground">
                          {`${item.confirmed_by_name}, ${formatDate(item.confirmed_at)}`}
                        </div>
                      ) : null}
                    </div>
                    <Pill tone={STATUS_TONE[item.status] ?? "neutral"}>
                      {STATUS_LABEL[item.status] ?? item.status}
                    </Pill>
                    {canAct && !current.closed_at ? (
                      <Confirm item={item} contractId={id} onSaved={setData} />
                    ) : null}
                  </div>
                ))}
              </div>
            </Card>
          ))}

          {canAct && !current.closed_at ? (
            <Card>
              <CardHeader
                title="Finish it"
                subtitle="Closing requires re-authentication, and refuses while anything above is open."
              />
              <CardBody>
                <Close closure={current} onClosed={setData} />
              </CardBody>
            </Card>
          ) : null}
        </>
      )}
    </div>
  );
}
