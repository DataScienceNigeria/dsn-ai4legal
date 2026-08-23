"use client";

import * as React from "react";

import { Icon } from "@/components/app/icons";
import { StepUpGate } from "@/components/app/step-up";
import { useRoles, useSession } from "@/components/app/session";
import { SuperDocEditor } from "@/components/app/superdoc-editor";
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
  Pill,
  Refusal,
  Select,
  Textarea,
} from "@/components/ui";
import { api, download, postForm } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Clause, Fallback } from "@/lib/types";
import { titleCase } from "@/lib/utils";

const AUTHORITIES = ["house", "fallback_1", "fallback_2", "fallback_3", "outside"];

type DiffLine = { kind: string; text: string };
type Diff = { from_reference: string; to_reference: string; lines: DiffLine[] };

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
      <Button size="sm" variant="dark" onClick={() => setOpen(true)}>
        <Icon name="rename" className="h-4 w-4" />
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
        <Icon name="review" className="h-4 w-4" />
        Publish
      </Button>
      <Button size="sm" variant="destructive" onClick={() => setConfirming("reject")}>
        <Icon name="trash" className="h-4 w-4" />
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
      <StepUpGate action="Publishing a library version" state={act} />
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
        <Icon name="compliance" className="h-4 w-4" />
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

type RequiredClause = {
  name: string;
  category: string;
  absent_severity: string;
};

const ABSENT_TONE: Record<string, "bad" | "warn" | "neutral"> = {
  critical: "bad",
  major: "warn",
  minor: "neutral",
};

/*
  A required clause is a record, not a string. Rendering it as one put an
  object where React expected text and an object where it expected a key, which
  is what took the whole templates screen down rather than just this dialog.
*/
export function PlaybookView({ agreementType }: Readonly<{ agreementType: string }>) {
  const [open, setOpen] = React.useState(false);
  const playbook = useApi<{
    name: string;
    version: number;
    required_clauses: RequiredClause[];
  }>(open ? `/playbooks/${agreementType}` : null, [agreementType, open]);

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        <Icon name="assessments" className="h-4 w-4" />
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
              <li
                key={`${clause.category}-${clause.name}`}
                className="flex flex-wrap items-center gap-2 rounded-md border p-2.5"
              >
                <Mono>{clause.category}</Mono>
                <span className="min-w-0 flex-1 font-medium">{clause.name}</span>
                <Pill tone={ABSENT_TONE[clause.absent_severity] ?? "neutral"}>
                  {titleCase(clause.absent_severity)} if absent
                </Pill>
              </li>
            ))}
          </ul>
          {playbook.data ? (
            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
              Version {playbook.data.version}. A clause marked critical stops issue outright;
              major and minor are reported and can be accepted with a reason.
            </p>
          ) : null}
        </DataState>
      </Modal>
    </>
  );
}

/*
  Anything the platform can serve as a .docx can be read in the app rather than
  downloaded and opened elsewhere. Viewing only: the authoritative copy is the
  one the API holds, and this surface is for reading a template or an import
  before deciding something about it.
*/
/*
  Proposing a version needs a clause to propose it against, so before this the
  library could only be revised, never extended. The first version is a draft
  like any other and still has to be published.
*/
const AGREEMENT_TYPES = [
  "nda_mutual",
  "master_services_agreement",
  "consultant_engagement",
  "data_sharing_agreement",
  "partnership_agreement",
  "lease_agreement",
  "ip_assignment",
  "other",
];

/*
  One upload, two things out of it. The document is kept as the document so it
  can be read and edited as itself, and the same file is split into blocks so
  generation has something deterministic to assemble from. Asking for the paper
  twice would be asking to let the two disagree.

  It arrives as a draft. Publishing is the separate, separately authorised
  step, so importing a file still cannot put anything into production.
*/
export function AddTemplate({ onDone }: Readonly<{ onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [agreementType, setAgreementType] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const input = React.useRef<HTMLInputElement>(null);

  const send = useAction(async () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("name", name.trim());
    form.append("agreement_type", agreementType);
    await postForm("/templates/import", form);
    onDone();
    setOpen(false);
    setName("");
    setAgreementType("");
    setFile(null);
  });

  const ready = file && name.trim() && agreementType;
  const errors = send.error?.fieldErrors ?? {};

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        <Icon name="plus" className="h-4 w-4" />
        Add template
      </Button>
      <Modal
        open={open}
        title="Add an agreement template"
        subtitle="Bring in a Word agreement you already use. It becomes a draft template you can read, change and publish."
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={!ready || send.busy} onClick={() => void send.run()}>
              {send.busy ? "Reading the document" : "Add it as a draft"}
            </Button>
          </>
        }
      >
        {send.error ? (
          <Refusal
            title="That template was not added"
            reason={send.error.message}
            reasons={Object.values(errors)}
          />
        ) : null}

        <Field label="What is it called" required error={errors.name}>
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Mutual non-disclosure agreement"
          />
        </Field>

        <Field
          label="Agreement type"
          required
          hint="What the platform routes and tiers on. It decides which playbook applies."
          error={errors.agreement_type}
        >
          <Select value={agreementType} onChange={(event) => setAgreementType(event.target.value)}>
            <option value="">Choose a type</option>
            {AGREEMENT_TYPES.map((value) => (
              <option key={value} value={value}>
                {titleCase(value)}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="The document" required error={errors.file}>
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={input}
              type="file"
              accept=".docx"
              className="hidden"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <Button size="sm" onClick={() => input.current?.click()}>
              Choose a .docx
            </Button>
            <span className="min-w-0 truncate text-sm text-muted-foreground">
              {file ? `${file.name}, ${Math.max(1, Math.round(file.size / 1024))} KB` : "Nothing chosen"}
            </span>
          </div>
        </Field>
      </Modal>
    </>
  );
}

export function NewClause({ onDone }: Readonly<{ onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [category, setCategory] = React.useState("");
  const [name, setName] = React.useState("");
  const [housePosition, setHousePosition] = React.useState("");
  const [unacceptable, setUnacceptable] = React.useState("");
  const [summary, setSummary] = React.useState("");

  const create = useAction(async () => {
    await api("/clauses", {
      method: "POST",
      body: {
        category: category.trim().toUpperCase(),
        name: name.trim(),
        house_position: housePosition.trim(),
        unacceptable_position: unacceptable.trim() || null,
        change_summary: summary.trim() || null,
      },
    });
    onDone();
    setOpen(false);
    setCategory("");
    setName("");
    setHousePosition("");
    setUnacceptable("");
    setSummary("");
  });

  const ready = category.trim() && name.trim() && housePosition.trim();
  const errors = create.error?.fieldErrors ?? {};

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        <Icon name="plus" className="h-4 w-4" />
        New clause
      </Button>
      <Modal
        open={open}
        title="Add a clause to the library"
        subtitle="A new category, with the first draft of its house position. It is a draft until someone with the authority publishes it."
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={!ready || create.busy} onClick={() => void create.run()}>
              {create.busy ? "Creating" : "Create the draft"}
            </Button>
          </>
        }
      >
        {create.error ? (
          <Refusal
            title="That clause was not created"
            reason={create.error.message}
            reasons={Object.values(errors)}
          />
        ) : null}

        <div className="grid gap-3 sm:grid-cols-[9rem_minmax(0,1fr)]">
          <Field label="Category" required hint="Short, upper case. CONF, LIAB, DPR." error={errors.category}>
            <Input
              value={category}
              onChange={(event) => setCategory(event.target.value.toUpperCase())}
              placeholder="TERM"
            />
          </Field>
          <Field label="Name" required error={errors.name}>
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Term and termination"
            />
          </Field>
        </div>

        <Field
          label="House position"
          required
          hint="The wording the organisation opens with. Fallbacks are added afterwards, as a version."
          error={errors.house_position}
        >
          <Textarea value={housePosition} onChange={(event) => setHousePosition(event.target.value)} />
        </Field>

        <Field label="Unacceptable position" hint="What may never be agreed, whoever asks.">
          <Textarea value={unacceptable} onChange={(event) => setUnacceptable(event.target.value)} />
        </Field>

        <Field label="Why this clause is needed">
          <Textarea value={summary} onChange={(event) => setSummary(event.target.value)} />
        </Field>
      </Modal>
    </>
  );
}

export function DocumentReader({
  source,
  name,
  title,
  subtitle,
  open,
  onClose,
}: Readonly<{
  source: string;
  name: string;
  title: string;
  subtitle: string;
  open: boolean;
  onClose: () => void;
}>) {
  const { me } = useSession();

  return (
    <Modal open={open} title={title} subtitle={subtitle} width="lg" onClose={onClose}>
      {open ? (
        <SuperDocEditor
          source={source}
          documentName={name}
          mode="viewing"
          exportable={false}
          user={{ name: me?.name ?? "Reader", email: me?.email ?? "" }}
        />
      ) : null}
    </Modal>
  );
}

export function CandidateReview({
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
  const [reading, setReading] = React.useState(false);

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
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border p-3">
        <span className="min-w-0 flex-1 text-sm text-muted-foreground">
          The split below is a proposal about a document. Read the document it came from before
          deciding what belongs in the library.
        </span>
        <Button size="sm" onClick={() => setReading(true)}>
          Read the source
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() =>
            void download(
              `/template-imports/${importId}/source`,
              detail.data?.filename ?? "import.docx",
            )
          }
        >
          Save
        </Button>
      </div>

      <DocumentReader
        open={reading}
        source={`/template-imports/${importId}/source`}
        name={detail.data?.filename ?? "Imported template"}
        title={detail.data?.filename ?? "The imported document"}
        subtitle="The Word file exactly as it was uploaded. Reading only."
        onClose={() => setReading(false)}
      />

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
