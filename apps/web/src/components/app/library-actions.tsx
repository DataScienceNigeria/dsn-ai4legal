"use client";

import * as React from "react";

import { useRoles } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Confirm,
  DataState,
  Empty,
  Field,
  Input,
  Modal,
  Mono,
  Notice,
  Pill,
  Refusal,
  Row,
  Select,
  Textarea,
} from "@/components/ui";
import { api, upload } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Clause, Fallback, Template } from "@/lib/types";
import { formatDateTime, titleCase } from "@/lib/utils";

const AUTHORITIES = ["house", "fallback_1", "fallback_2", "fallback_3", "outside"];

type DiffLine = { kind: string; text: string };
type Diff = { from_reference: string; to_reference: string; lines: DiffLine[] };

type ImportRow = {
  id: string;
  filename: string;
  agreement_type: string | null;
  status: string;
  candidate_count: number;
  accepted_count: number;
  created_at: string;
};

type Candidate = {
  number: string;
  heading: string;
  text: string;
  proposed_category: string | null;
  confidence: number;
  decision: string;
  created_version?: string;
};

/*
  A proposal never edits a version in place. It creates a draft that carries
  the change summary, and the draft only becomes house position when the head
  of legal publishes it after a fresh authentication.
*/
export function ProposeVersion({
  kind,
  code,
  current,
  onDone,
}: Readonly<{
  kind: "clause" | "template";
  code: string;
  current: { house_position?: string; unacceptable_position?: string | null; fallbacks?: Fallback[] } | null;
  onDone: () => void;
}>) {
  const [open, setOpen] = React.useState(false);
  const [summary, setSummary] = React.useState("");
  const [housePosition, setHousePosition] = React.useState("");
  const [unacceptable, setUnacceptable] = React.useState("");
  const [fallbacks, setFallbacks] = React.useState<(Fallback & { id: string })[]>([]);
  const [effective, setEffective] = React.useState("");
  const [review, setReview] = React.useState("");

  React.useEffect(() => {
    if (!open) return;
    setHousePosition(current?.house_position ?? "");
    setUnacceptable(current?.unacceptable_position ?? "");
    setFallbacks(
      (current?.fallbacks ?? []).map((fallback) => ({
        ...fallback,
        id: crypto.randomUUID(),
      })),
    );
  }, [open, current]);

  const propose = useAction(async () => {
    const path = kind === "clause" ? `/clauses/${code}/versions` : `/templates/${code}/versions`;
    await api(path, {
      method: "POST",
      body: {
        change_summary: summary,
        house_position: housePosition || undefined,
        unacceptable_position: unacceptable || undefined,
        fallbacks: fallbacks.length ? fallbacks : undefined,
        effective_date: effective || undefined,
        review_date: review || undefined,
      },
    });
    onDone();
    setOpen(false);
    setSummary("");
  });

  const updateFallback = (index: number, key: keyof Fallback, value: string) =>
    setFallbacks((previous) =>
      previous.map((fallback, position) =>
        position === index ? { ...fallback, [key]: value } : fallback,
      ),
    );

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Propose a change
      </Button>
      <Modal
        open={open}
        title={`Propose a new ${kind} version`}
        subtitle="This creates a draft. It is not house position and cannot generate anything until it is published."
        width="lg"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={summary.trim().length < 10 || propose.busy}
              onClick={() => void propose.run()}
            >
              Create the draft
            </Button>
          </>
        }
      >
        <Field label="What is changing and why" required hint="This becomes the provenance line on the version.">
          <Textarea value={summary} onChange={(event) => setSummary(event.target.value)} />
        </Field>

        {kind === "clause" ? (
          <>
            <Field label="House position" hint="Left as it is, the current wording carries over.">
              <Textarea
                value={housePosition}
                onChange={(event) => setHousePosition(event.target.value)}
                className="min-h-[7rem]"
              />
            </Field>

            <div className="space-y-2">
              <div className="text-sm font-medium">Ranked fallbacks</div>
              <p className="text-sm text-muted-foreground">
                Each fallback names the authority needed to concede it. That is what turns a
                negotiation into a decision someone is accountable for.
              </p>
              {fallbacks.map((fallback, index) => (
                <div key={fallback.id} className="space-y-2 rounded-md border p-3">
                  <div className="grid gap-2 sm:grid-cols-[6rem_minmax(0,1fr)]">
                    <Field label="Rank">
                      <Input
                        type="number"
                        value={fallback.rank}
                        onChange={(event) => updateFallback(index, "rank", event.target.value)}
                      />
                    </Field>
                    <Field label="Authority to concede">
                      <Select
                        value={fallback.required_authority}
                        onChange={(event) =>
                          updateFallback(index, "required_authority", event.target.value)
                        }
                      >
                        {AUTHORITIES.map((value) => (
                          <option key={value} value={value}>
                            {titleCase(value)}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </div>
                  <Field label="Wording">
                    <Textarea
                      value={fallback.text}
                      onChange={(event) => updateFallback(index, "text", event.target.value)}
                    />
                  </Field>
                </div>
              ))}
              <Button
                size="sm"
                onClick={() =>
                  setFallbacks((previous) => [
                    ...previous,
                    {
                      id: crypto.randomUUID(),
                      rank: previous.length + 1,
                      text: "",
                      required_authority: "fallback_1",
                    },
                  ])
                }
              >
                Add a fallback
              </Button>
            </div>

            <Field label="Unacceptable position" hint="What may never be agreed, whoever asks.">
              <Textarea value={unacceptable} onChange={(event) => setUnacceptable(event.target.value)} />
            </Field>
          </>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Effective from" hint="Left blank, it takes effect on publication.">
            <Input type="date" value={effective} onChange={(event) => setEffective(event.target.value)} />
          </Field>
          <Field label="Review due">
            <Input type="date" value={review} onChange={(event) => setReview(event.target.value)} />
          </Field>
        </div>

        {propose.error ? (
          <Refusal
            title="That proposal was refused"
            reason={propose.error.message}
            reasons={propose.error.reasons}
          />
        ) : null}
      </Modal>
    </>
  );
}

export function VersionDecision({
  reference,
  status,
  onDone,
}: Readonly<{ reference: string; status: string; onDone: () => void }>) {
  const { has } = useRoles();
  const [confirming, setConfirming] = React.useState<"publish" | "reject" | null>(null);

  const act = useAction(async (action: string) => {
    await api(`/versions/${reference}/${action}`, { method: "POST" });
    onDone();
    setConfirming(null);
  });

  if (status !== "draft" || !has("head_of_legal", "admin")) return null;

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => setConfirming("publish")}>
        Publish
      </Button>
      <Button size="sm" variant="destructive" onClick={() => setConfirming("reject")}>
        Reject
      </Button>
      <Confirm
        open={confirming === "publish"}
        title={`Publish ${reference}`}
        detail="The previous version is superseded atomically and stays readable. Publication needs a fresh authentication, so you may be asked to sign in again."
        confirmLabel="Publish it"
        busy={act.busy}
        error={act.error?.message}
        onCancel={() => setConfirming(null)}
        onConfirm={() => void act.run("publish")}
      />
      <Confirm
        open={confirming === "reject"}
        title={`Reject ${reference}`}
        detail="The draft is withdrawn. The version in force is unchanged."
        confirmLabel="Withdraw it"
        destructive
        busy={act.busy}
        error={act.error?.message}
        onCancel={() => setConfirming(null)}
        onConfirm={() => void act.run("reject")}
      />
    </>
  );
}

export function ClauseDiff({ category }: Readonly<{ category: string }>) {
  const [open, setOpen] = React.useState(false);
  const diff = useApi<Diff>(open ? `/clauses/${category}/diff` : null, [category, open]);

  const toneFor = (kind: string) => {
    if (kind === "added") return "border-primary/30 bg-primary/10";
    if (kind === "removed") return "border-destructive/30 bg-destructive/10 line-through";
    return "border-transparent";
  };

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        What changed
      </Button>
      <Modal
        open={open}
        title="What changed in this clause"
        subtitle={
          diff.data
            ? `${diff.data.from_reference} against ${diff.data.to_reference}`
            : "Comparing the version in force with the one before it."
        }
        width="lg"
        onClose={() => setOpen(false)}
      >
        <DataState
          loading={diff.loading}
          errorMessage={diff.error?.message}
          errorTitle="There is nothing to compare"
          isEmpty={(diff.data?.lines ?? []).length === 0}
          emptyTitle="This clause has only ever had one version"
        >
          <div className="space-y-1 font-mono text-xs">
            {(diff.data?.lines ?? []).map((line, index) => (
              <div
                key={`${line.kind}-${index}-${line.text.slice(0, 24)}`}
                className={`rounded-sm border px-2 py-1 leading-relaxed ${toneFor(line.kind)}`}
              >
                {line.text}
              </div>
            ))}
          </div>
        </DataState>
      </Modal>
    </>
  );
}

export function PlaybookView({ agreementType }: Readonly<{ agreementType: string }>) {
  const [open, setOpen] = React.useState(false);
  const playbook = useApi<{
    name: string;
    version: number;
    required_clauses: string[];
  }>(open ? `/playbooks/${agreementType}` : null, [agreementType, open]);

  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        Playbook
      </Button>
      <Modal
        open={open}
        title={playbook.data?.name ?? `Playbook for ${titleCase(agreementType)}`}
        subtitle="What every agreement of this type has to contain before it can be issued."
        onClose={() => setOpen(false)}
      >
        <DataState
          loading={playbook.loading}
          errorMessage={playbook.error?.message}
          errorTitle="No playbook is published for that agreement type"
          isEmpty={false}
        >
          <ul className="space-y-1.5 text-sm">
            {(playbook.data?.required_clauses ?? []).map((clause) => (
              <li key={clause} className="flex items-center gap-2">
                <Pill tone="info">Required</Pill>
                <Mono>{clause}</Mono>
              </li>
            ))}
          </ul>
        </DataState>
      </Modal>
    </>
  );
}

function CandidateReview({
  importId,
  onDone,
  onClose,
}: Readonly<{ importId: string; onDone: () => void; onClose: () => void }>) {
  const detail = useApi<{ filename: string; candidates: Candidate[] }>(
    `/template-imports/${importId}`,
    [importId],
  );
  const [decisions, setDecisions] = React.useState<Record<number, string>>({});
  const [categories, setCategories] = React.useState<Record<number, string>>({});

  const accept = useAction(async () => {
    const accepted = Object.entries(decisions)
      .filter(([, value]) => value === "accept")
      .map(([index]) => ({
        index: Number(index),
        category: categories[Number(index)] || undefined,
      }));
    const rejected = Object.entries(decisions)
      .filter(([, value]) => value === "reject")
      .map(([index]) => Number(index));
    await api(`/template-imports/${importId}/accept`, {
      method: "POST",
      body: { accepted, rejected },
    });
    onDone();
    onClose();
  });

  const candidates = detail.data?.candidates ?? [];
  const decided = Object.keys(decisions).length;

  return (
    <Modal
      open
      title={`Review ${detail.data?.filename ?? "this import"}`}
      subtitle="Everything accepted becomes a draft clause version. Nothing imported is house position until it is published."
      width="lg"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={decided === 0 || accept.busy} onClick={() => void accept.run()}>
            Record {decided} decisions
          </Button>
        </>
      }
    >
      {accept.error ? (
        <Refusal title="Those decisions were refused" reason={accept.error.message} reasons={accept.error.reasons} />
      ) : null}
      <DataState
        loading={detail.loading}
        errorMessage={detail.error?.message}
        isEmpty={candidates.length === 0}
        emptyTitle="This import produced no candidate clauses"
      >
        <div className="space-y-3">
          {candidates.map((candidate, index) => (
            <div
              key={`${candidate.number}-${candidate.heading}-${index}`}
              className="space-y-2 rounded-md border p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold">
                  {candidate.number} {candidate.heading}
                </span>
                <Pill tone={candidate.confidence >= 0.7 ? "good" : "warn"}>
                  {Math.round(candidate.confidence * 100)}% confident
                </Pill>
                {candidate.decision === "pending" ? null : (
                  <Pill tone={candidate.decision === "accepted" ? "good" : "neutral"}>
                    Already {candidate.decision}
                    {candidate.created_version ? `, ${candidate.created_version}` : ""}
                  </Pill>
                )}
              </div>
              <p className="max-h-40 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                {candidate.text}
              </p>
              {candidate.decision === "pending" ? (
                <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
                  <Input
                    placeholder="Clause category"
                    value={categories[index] ?? candidate.proposed_category ?? ""}
                    onChange={(event) =>
                      setCategories((previous) => ({ ...previous, [index]: event.target.value }))
                    }
                  />
                  <Button
                    variant={decisions[index] === "accept" ? "primary" : "default"}
                    onClick={() => setDecisions((previous) => ({ ...previous, [index]: "accept" }))}
                  >
                    Accept
                  </Button>
                  <Button
                    variant={decisions[index] === "reject" ? "destructive" : "default"}
                    onClick={() => setDecisions((previous) => ({ ...previous, [index]: "reject" }))}
                  >
                    Reject
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </DataState>
    </Modal>
  );
}

export function TemplateImports() {
  const { has } = useRoles();
  const imports = useApi<ImportRow[]>("/template-imports");
  const [reviewing, setReviewing] = React.useState<string | null>(null);
  const [agreementType, setAgreementType] = React.useState("");
  const fileInput = React.useRef<HTMLInputElement>(null);

  const send = useAction(async (file: File) => {
    const suffix = agreementType ? `?agreement_type=${encodeURIComponent(agreementType)}` : "";
    await upload(`/template-imports${suffix}`, file);
    imports.reload();
  });

  const rows = imports.data ?? [];
  const cols = "minmax(0,1fr) 9.375rem 7.5rem 7.5rem 9.375rem 7.5rem";

  return (
    <div className="space-y-4">
      <Notice tone="info" title="Importing a Word template does not publish anything">
        The file is broken into candidate clauses, each with a proposed category and a confidence.
        A human decides on every one, and each acceptance produces a draft, never house position.
      </Notice>

      {send.error ? (
        <Refusal title="That file was not imported" reason={send.error.message} reasons={send.error.reasons} />
      ) : null}

      <Card>
        <CardHeader
          title="Word template imports"
          actions={
            has("head_of_legal", "counsel", "admin") ? (
              <>
                <Input
                  className="w-48"
                  placeholder="Agreement type"
                  value={agreementType}
                  onChange={(event) => setAgreementType(event.target.value)}
                />
                <input
                  ref={fileInput}
                  type="file"
                  accept=".docx"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void send.run(file);
                    event.target.value = "";
                  }}
                />
                <Button variant="primary" disabled={send.busy} onClick={() => fileInput.current?.click()}>
                  {send.busy ? "Reading the file" : "Import a .docx"}
                </Button>
              </>
            ) : null
          }
        />
        <div className="table-scroll">
          <div className="min-w-[56.25rem]">
            <Row cols={cols} head>
              <div>File</div>
              <div>Agreement type</div>
              <div>Status</div>
              <div>Candidates</div>
              <div>Imported</div>
              <div>Action</div>
            </Row>
            <DataState
              loading={imports.loading}
              errorMessage={imports.error?.message}
              isEmpty={rows.length === 0}
              emptyTitle="No Word template has been imported"
            >
              {rows.map((row) => (
                <Row key={row.id} cols={cols}>
                  <div className="min-w-0 truncate text-sm font-medium">{row.filename}</div>
                  <div className="text-sm">{titleCase(row.agreement_type ?? "not stated")}</div>
                  <div>
                    <Pill tone={row.status === "decided" ? "good" : "warn"}>{titleCase(row.status)}</Pill>
                  </div>
                  <div className="text-sm">
                    {row.accepted_count} of {row.candidate_count}
                  </div>
                  <div className="text-xs text-muted-foreground">{formatDateTime(row.created_at)}</div>
                  <div>
                    <Button size="sm" onClick={() => setReviewing(row.id)}>
                      Review
                    </Button>
                  </div>
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>

      {reviewing ? (
        <CandidateReview
          importId={reviewing}
          onDone={() => imports.reload()}
          onClose={() => setReviewing(null)}
        />
      ) : null}
    </div>
  );
}

export function TemplateDetail({
  code,
  onChanged,
}: Readonly<{ code: string; onChanged: () => void }>) {
  const template = useApi<Template>(`/templates/${code}`, [code]);
  const { has } = useRoles();
  const data = template.data;

  return (
    <Card>
      <CardHeader
        title={data?.name ?? code}
        subtitle={
          data ? (
            <span className="flex flex-wrap items-center gap-2">
              <Mono>{data.current?.reference ?? "No approved version"}</Mono>
              <span>{titleCase(data.agreement_type)}</span>
              <span>{data.jurisdiction}</span>
            </span>
          ) : null
        }
        actions={
          <>
            {data ? <PlaybookView agreementType={data.agreement_type} /> : null}
            {has("counsel", "head_of_legal", "admin") ? (
              <ProposeVersion
                kind="template"
                code={code}
                current={null}
                onDone={() => {
                  template.reload();
                  onChanged();
                }}
              />
            ) : null}
          </>
        }
      />
      <CardBody>
        <DataState
          loading={template.loading}
          errorMessage={template.error?.message}
          isEmpty={(data?.versions ?? []).length === 0}
          emptyTitle="This template has no versions"
        >
          <div className="space-y-2">
            {(data?.versions ?? []).map((version) => (
              <div
                key={version.id}
                className="flex flex-wrap items-center gap-2 rounded-md border p-3"
              >
                <Mono>{version.reference}</Mono>
                <Pill tone={version.status === "approved" ? "good" : "neutral"}>
                  {titleCase(version.status)}
                </Pill>
                <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
                  {version.change_summary ?? "No change summary was recorded"}
                </span>
                <VersionDecision
                  reference={version.reference}
                  status={version.status}
                  onDone={() => {
                    template.reload();
                    onChanged();
                  }}
                />
              </div>
            ))}
          </div>
        </DataState>
      </CardBody>
    </Card>
  );
}

export function ClauseVersionList({
  clause,
  onChanged,
}: Readonly<{ clause: Clause; onChanged: () => void }>) {
  return (
    <Card>
      <CardHeader
        title="Version history"
        subtitle="Superseded versions are never deleted, and a draft is not house position."
        actions={<ClauseDiff category={clause.category} />}
      />
      <CardBody>
        {clause.versions.length === 0 ? (
          <Empty title="This clause has no versions" />
        ) : (
          <div className="space-y-2">
            {clause.versions.map((version) => (
              <div key={version.id} className="flex flex-wrap items-center gap-2 rounded-md border p-3">
                <Mono>{version.reference}</Mono>
                <Pill tone={version.status === "approved" ? "good" : "neutral"}>
                  {titleCase(version.status)}
                </Pill>
                <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
                  {version.house_position}
                </span>
                <VersionDecision reference={version.reference} status={version.status} onDone={onChanged} />
              </div>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
