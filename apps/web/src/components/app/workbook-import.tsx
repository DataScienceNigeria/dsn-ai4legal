"use client";

import Link from "next/link";
import * as React from "react";

import { Icon } from "@/components/app/icons";
import { ABSENT_TONE, ProposeVersion, VersionDecision } from "@/components/app/library-actions";
import { useRoles } from "@/components/app/session";
import { StepUpGate } from "@/components/app/step-up";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Confirm,
  DataState,
  Empty,
  Field,
  Kpi,
  Mono,
  Notice,
  Pill,
  Refusal,
  Row,
  Select,
} from "@/components/ui";
import { api, download, upload } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Clause, ClauseVariant, ClauseVersion, Playbook, WorkbookImport, WorkbookIssue } from "@/lib/types";
import { formatDate, formatDateTime, titleCase } from "@/lib/utils";

const MAX_UPLOAD_MB = 50;
const ENTITY_LABEL: Record<string, string> = { DSN: "DSN", EAI: "EqualyzAI", BOTH: "Both entities" };

export function workbookFileProblem(file: File | null): string | null {
  if (!file) return "Choose the workbook to check.";
  if (!file.name.toLowerCase().endsWith(".xlsx")) return "Upload the workbook as an Excel .xlsx file.";
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `The file is larger than the ${MAX_UPLOAD_MB} MB limit.`;
  return null;
}

export function ExportWorkbook() {
  const save = useAction(async () => {
    await download("/library/export", `Legal Playbook and Clause Library ${new Date().toISOString().slice(0, 10)}.xlsx`);
  });
  return (
    <>
      <Button size="sm" disabled={save.busy} onClick={() => void save.run()}>
        <Icon name="archive" className="h-4 w-4" />
        {save.busy ? "Preparing the workbook" : "Export workbook"}
      </Button>
      {save.error ? <span className="text-xs text-destructive">{save.error.message}</span> : null}
    </>
  );
}

function variantLabel(variant: ClauseVariant): string {
  const type = variant.agreement_type === "all" ? "All agreements" : titleCase(variant.agreement_type);
  return [ENTITY_LABEL[variant.entity_scope] ?? variant.entity_scope, type, variant.subtype].filter(Boolean).join(", ");
}

function latestOf(variant: ClauseVariant): ClauseVersion | null {
  return (
    variant.versions.find((version) => version.status === "draft") ??
    variant.current ??
    null
  );
}

function Positions({ version }: Readonly<{ version: ClauseVersion }>) {
  return (
    <div className="space-y-4">
      {version.standard_position ? (
        <div>
          <div className="mb-1.5 text-xs font-semibold text-muted-foreground">STANDARD POSITION</div>
          <p className="text-sm leading-relaxed">{version.standard_position}</p>
        </div>
      ) : null}
      <div>
        <div className="mb-1.5 text-xs font-semibold text-muted-foreground">CLAUSE WORDING</div>
        <p
          className={`whitespace-pre-line rounded-md border p-3 text-sm leading-relaxed ${
            version.status === "approved" ? "border-brand/20 bg-brand/5" : "border-warning/40 bg-warning/5"
          }`}
        >
          {version.house_position}
        </p>
      </div>
      {version.fallbacks.length ? (
        <div className="space-y-2">
          <div className="text-xs font-semibold text-muted-foreground">
            NEGOTIATED AND FALLBACK POSITIONS, WITH THE AUTHORITY NEEDED TO CONCEDE
          </div>
          {version.fallbacks.map((fallback) => (
            <div key={fallback.rank} className="rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone="info">{fallback.rank === 1 ? "Negotiated" : `Fallback ${fallback.rank - 1}`}</Pill>
                <span className="text-xs text-muted-foreground">
                  {fallback.required_authority === "fallback_1" ? "Legal" : "Legal lead"}
                </span>
              </div>
              <p className="mt-1.5 text-sm leading-relaxed">{fallback.text}</p>
            </div>
          ))}
        </div>
      ) : (
        <Notice tone="neutral" title="No negotiated position or fallback">
          Any departure from the standard position needs the legal lead.
        </Notice>
      )}
      {version.unacceptable_position ? (
        <div>
          <div className="mb-1.5 text-xs font-semibold text-muted-foreground">RED LINE</div>
          <p className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm leading-relaxed">
            {version.unacceptable_position}
          </p>
        </div>
      ) : null}
      {version.provenance ? <p className="text-xs text-muted-foreground">{version.provenance}</p> : null}
    </div>
  );
}

export function ClauseVariants({
  clause,
  canPropose,
  onChanged,
}: Readonly<{ clause: Clause; canPropose: boolean; onChanged: () => void }>) {
  const variants = clause.variants ?? [];
  const [selected, setSelected] = React.useState<string>("");
  const variant = variants.find((item) => item.code === selected) ?? variants[0];

  if (!variant) {
    return <Empty title="No variant of this clause applies to this entity" />;
  }
  const shown = latestOf(variant);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title={clause.name}
          subtitle={
            <span className="flex flex-wrap items-center gap-2">
              <Mono>{clause.category}</Mono>
              {clause.family ? <span>{clause.family}</span> : null}
              <span>
                {variants.length} {variants.length === 1 ? "variant" : "variants"} in this entity
              </span>
            </span>
          }
        />
        <CardBody className="space-y-4">
          {variants.length > 1 ? (
            <Field label="Variant" hint="One wording per entity, agreement type and role.">
              <Select value={variant.code} onChange={(event) => setSelected(event.target.value)}>
                {variants.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.code}, {item.title} ({variantLabel(item)})
                  </option>
                ))}
              </Select>
            </Field>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{variant.title}</span>
            <Mono>{variant.code}</Mono>
            <span className="text-xs text-muted-foreground">
              {variantLabel(variant)}, {variant.transaction_role}
            </span>
            {variant.source_url ? (
              <a
                href={variant.source_url}
                target="_blank"
                rel="noreferrer noopener"
                className="text-xs underline underline-offset-2"
              >
                Source
              </a>
            ) : null}
          </div>

          {shown ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Mono>{shown.reference}</Mono>
                <Pill tone={shown.status === "approved" ? "good" : "warn"}>
                  {shown.status === "approved" ? "House position" : "Draft, not house position"}
                </Pill>
                {shown.review_date ? (
                  <span className="text-xs text-muted-foreground">Review due {formatDate(shown.review_date)}</span>
                ) : null}
                <div className="ml-auto flex flex-wrap gap-2">
                  {canPropose && !variant.versions.some((v) => v.status === "draft") ? (
                    <ProposeVersion kind="variant" code={variant.code} current={shown} onDone={onChanged} />
                  ) : null}
                  <VersionDecision reference={shown.reference} status={shown.status} onDone={onChanged} />
                </div>
              </div>
              <Positions version={shown} />
            </>
          ) : (
            <Empty title="This variant has no version in force or in draft" />
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Version history" subtitle="Superseded versions are never deleted." />
        <CardBody className="space-y-2">
          {variant.versions.map((version) => (
            <div key={version.id} className="flex flex-wrap items-center gap-2 rounded-md border p-3">
              <Mono>{version.reference}</Mono>
              <Pill tone={version.status === "approved" ? "good" : "neutral"}>{titleCase(version.status)}</Pill>
              <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
                {version.provenance ?? version.house_position}
              </span>
            </div>
          ))}
        </CardBody>
      </Card>
    </div>
  );
}

function PublishPlaybook({ playbook, onDone }: Readonly<{ playbook: Playbook; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const act = useAction(async () => {
    await api(`/playbooks/${playbook.id}/publish`, { method: "POST" });
    setOpen(false);
    onDone();
  });
  const drafts = playbook.drafts ?? 0;
  if (playbook.required_clauses.length === 0) {
    return <span className="text-xs text-muted-foreground">No approved wording yet</span>;
  }
  if (playbook.active && drafts === 0) return null;

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        <Icon name="review" className="h-4 w-4" />
        Publish
      </Button>
      <Confirm
        open={open}
        title={`Publish ${playbook.name}`}
        detail={`${drafts} draft clause ${drafts === 1 ? "version becomes" : "versions become"} house position, each superseding the version it replaces, and the playbook is used for review. Read the drafts first. You may be asked to sign in again.`}
        confirmLabel="Publish the playbook"
        busy={act.busy}
        error={act.error ? [act.error.message, ...act.error.reasons].join(" ") : null}
        onCancel={() => setOpen(false)}
        onConfirm={() => void act.run()}
      />
      <StepUpGate action="Publishing a playbook" state={act} />
    </>
  );
}

export function PlaybookList({ entity }: Readonly<{ entity: string }>) {
  const { has } = useRoles();
  const canPublish = has("head_of_legal", "admin");
  const playbooks = useApi<Playbook[]>("/playbooks", [entity]);
  const [open, setOpen] = React.useState<string | null>(null);

  return (
    <Card>
      <CardHeader
        title="Playbooks"
        subtitle="One per entity and agreement sub-type. A playbook is used for review only once it is published."
      />
      <DataState
        loading={playbooks.loading}
        errorMessage={playbooks.error?.message}
        errorTitle="The playbooks could not be loaded"
        isEmpty={!playbooks.data?.length}
        emptyTitle="No playbook applies to this entity yet"
      >
        <Row cols="minmax(0,1fr) 6rem 7rem 9rem 8rem" head>
          <div>Playbook</div>
          <div>Clauses</div>
          <div>Drafts</div>
          <div>Status</div>
          <div />
        </Row>
        {(playbooks.data ?? []).map((playbook) => (
          <React.Fragment key={playbook.id}>
            <Row cols="minmax(0,1fr) 6rem 7rem 9rem 8rem">
              <button
                type="button"
                className="min-w-0 text-left"
                onClick={() => setOpen(open === playbook.id ? null : playbook.id)}
                aria-expanded={open === playbook.id}
              >
                <div className="truncate text-sm font-medium">{playbook.name}</div>
                <div className="text-xs text-muted-foreground">
                  {titleCase(playbook.agreement_type)}
                  {playbook.subtype ? `, ${playbook.subtype}` : ""}, version {playbook.version}
                </div>
              </button>
              <div className="text-sm">{playbook.required_clauses.length}</div>
              <div className="text-sm">{playbook.drafts ?? 0}</div>
              <div>
                <Pill tone={playbook.active ? "good" : "warn"}>{playbook.active ? "In use" : "Not published"}</Pill>
              </div>
              <div className="flex justify-end">
                {canPublish ? <PublishPlaybook playbook={playbook} onDone={() => playbooks.reload()} /> : null}
              </div>
            </Row>
            {open === playbook.id ? (
              <ul className="space-y-1.5 border-b bg-muted/30 px-4 py-3 text-sm sm:px-5">
                {playbook.required_clauses.map((clause) => (
                  <li key={clause.variant ?? clause.category} className="flex flex-wrap items-center gap-2">
                    <Mono>{clause.variant ?? clause.category}</Mono>
                    <span className="min-w-0 flex-1">{clause.name}</span>
                    {clause.family ? <span className="text-xs text-muted-foreground">{clause.family}</span> : null}
                    <Pill tone={ABSENT_TONE[clause.absent_severity] ?? "neutral"}>
                      {titleCase(clause.absent_severity)} if absent
                    </Pill>
                  </li>
                ))}
              </ul>
            ) : null}
          </React.Fragment>
        ))}
      </DataState>
      {canPublish ? null : (
        <CardBody>
          <p className="text-xs text-muted-foreground">Publishing a playbook needs the Head of Legal or an administrator.</p>
        </CardBody>
      )}
    </Card>
  );
}

const SUMMARY_LABELS: [string, string][] = [
  ["clauses", "Clauses"],
  ["variants", "Clause versions"],
  ["precedents", "Precedent wording"],
  ["playbooks", "Playbooks"],
];

function changeLine(summary: Record<string, number>, kind: string): string {
  const parts = ["new", "changed", "relabelled", "unchanged", "blocked"]
    .map((outcome) => [outcome, summary[`${kind}_${outcome}`] ?? 0] as const)
    .filter(([, count]) => count > 0)
    .map(([outcome, count]) => `${count} ${outcome}`);
  return parts.join(", ") || "nothing to change";
}

function IssueList({ issues }: Readonly<{ issues: WorkbookIssue[] }>) {
  const [sheet, setSheet] = React.useState("all");
  const [level, setLevel] = React.useState("all");
  const sheets = Array.from(new Set(issues.map((issue) => issue.sheet)));

  const shown = issues.filter(
    (issue) => (sheet === "all" || issue.sheet === sheet) && (level === "all" || issue.level === level),
  );
  const rows = new Map<string, WorkbookIssue[]>();
  for (const issue of shown) {
    const key = `${issue.sheet}|${issue.row ?? ""}`;
    rows.set(key, [...(rows.get(key) ?? []), issue]);
  }
  const ordered = Array.from(rows.values()).sort(
    (a, b) =>
      Number(b.some((i) => i.level === "error")) - Number(a.some((i) => i.level === "error")) ||
      a[0].sheet.localeCompare(b[0].sheet) ||
      (a[0].row ?? 0) - (b[0].row ?? 0),
  );

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Sheet">
          <Select value={sheet} onChange={(event) => setSheet(event.target.value)}>
            <option value="all">All sheets</option>
            {sheets.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Show">
          <Select value={level} onChange={(event) => setLevel(event.target.value)}>
            <option value="all">All problems</option>
            <option value="error">Errors only</option>
            <option value="warning">Warnings only</option>
          </Select>
        </Field>
      </div>
      {ordered.length === 0 ? (
        <Empty title="Nothing to show for this filter" />
      ) : (
        <ul className="max-h-[32rem] space-y-2 overflow-y-auto">
          {ordered.map((group) => {
            const failed = group.some((issue) => issue.level === "error");
            return (
              <li
                key={`${group[0].sheet}-${group[0].row}`}
                className={`rounded-md border p-3 ${
                  failed ? "border-destructive/40 bg-destructive/5" : "border-warning/40 bg-warning/5"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                  <Pill tone={failed ? "bad" : "warn"}>{failed ? "Error" : "Warning"}</Pill>
                  <span>
                    {group[0].sheet}
                    {group[0].row ? `, row ${group[0].row}` : ""}
                  </span>
                </div>
                <ul className="mt-1.5 space-y-1 text-sm">
                  {group.map((issue) => (
                    <li
                      key={`${issue.column}-${issue.message}`}
                      className={issue.level === "error" ? "text-destructive" : "text-foreground"}
                    >
                      {issue.column ? <span className="font-medium">{issue.column}: </span> : null}
                      {issue.message}
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function CheckResult({
  record,
  onApplied,
}: Readonly<{ record: WorkbookImport; onApplied: (record: WorkbookImport) => void }>) {
  const { has } = useRoles();
  const canApply = has("head_of_legal", "admin");
  const [confirming, setConfirming] = React.useState(false);
  const [leaveOut, setLeaveOut] = React.useState(false);
  const [playbook, setPlaybook] = React.useState("");
  const apply = useAction(async () => {
    const result = await api<WorkbookImport>(`/library/imports/${record.id}/apply`, {
      method: "POST",
      body: { exclude_errors: leaveOut, playbook: playbook || undefined },
    });
    setConfirming(false);
    onApplied(result);
  });
  const summary = record.summary ?? {};
  const pilot = record.playbooks.find((item) => item.key === playbook);
  const rows = record.excluded_rows;

  const blocked =
    record.status !== "checked"
      ? `This check was ${record.status}. Upload the workbook again to check it against the library as it is now.`
      : record.structural
        ? "The workbook itself cannot be read as it is. Fix the problem listed above and upload it again."
        : !canApply
          ? "Applying needs the Head of Legal or an administrator. Share this check with them."
          : rows > 0 && !leaveOut
            ? `${rows} ${rows === 1 ? "row has" : "rows have"} errors. Fix them and upload again, or confirm below that they are left out.`
            : null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title={record.filename}
          subtitle={`Checked ${formatDateTime(record.created_at)}${record.uploaded_by ? ` by ${record.uploaded_by}` : ""}`}
        />
        <CardBody className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {SUMMARY_LABELS.map(([key, label]) => (
              <Kpi key={key} label={label} value={summary[key] ?? 0} />
            ))}
          </div>
          <ul className="space-y-1 text-sm">
            <li>Clause versions: {changeLine(summary, "variants")}.</li>
            <li>Precedent wording: {changeLine(summary, "precedents")}, of which {summary.prohibited ?? 0} prohibited.</li>
            <li>Playbooks: {changeLine(summary, "playbooks")}.</li>
            <li>{summary.without_fallbacks ?? 0} clause versions have no negotiated position, fallback or red line.</li>
            <li>
              {summary.variants_without_source ?? 0} clause versions have no Source and cannot be published
              until one is added. {summary.precedents_without_source ?? 0} precedent wordings have no Source
              and are kept out of memory.
            </li>
          </ul>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title={
            record.errors
              ? `${record.errors} ${record.errors === 1 ? "error" : "errors"} on ${record.excluded_rows} ${record.excluded_rows === 1 ? "row" : "rows"}, ${record.warnings} warnings`
              : `No errors, ${record.warnings} warnings`
          }
          subtitle="A row with an error is not loaded. Warnings are loaded as stated and listed for the legal team to review."
        />
        <CardBody>
          {record.issues?.length ? <IssueList issues={record.issues} /> : <Empty title="Every row is clean" />}
        </CardBody>
      </Card>

      {record.status === "checked" && !record.structural && canApply ? (
        <Card>
          <CardBody className="space-y-3">
            <Field
              label="What to load"
              hint="Load one playbook first to check its classifications, publication and review before the rest."
            >
              <Select value={playbook} onChange={(event) => setPlaybook(event.target.value)}>
                <option value="">All playbooks and all precedent</option>
                {record.playbooks.map((item) => (
                  <option key={item.key} value={item.key}>
                    Only {item.name} ({item.clauses} clauses)
                  </option>
                ))}
              </Select>
            </Field>
            {rows > 0 ? (
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={leaveOut}
                  onChange={(event) => setLeaveOut(event.target.checked)}
                />
                <span>
                  Load the valid rows and leave out the {rows} {rows === 1 ? "row" : "rows"} with errors.
                  They stay listed against this check, and a playbook that already requires one of
                  those clauses keeps requiring it.
                </span>
              </label>
            ) : null}
          </CardBody>
        </Card>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          disabled={Boolean(blocked) || apply.busy}
          onClick={() => setConfirming(true)}
          aria-describedby="apply-blocked"
        >
          {pilot ? "Load this playbook as drafts" : "Apply as drafts"}
        </Button>
        {blocked ? (
          <span id="apply-blocked" className="text-sm text-destructive">
            {blocked}
          </span>
        ) : (
          <span className="text-sm text-muted-foreground">
            Everything lands as a draft. Nothing is house position until a playbook is published.
          </span>
        )}
      </div>
      {apply.error ? (
        <Refusal title="Nothing was written" reason={apply.error.message} reasons={apply.error.reasons} />
      ) : null}
      <Confirm
        open={confirming}
        title={pilot ? `Load ${pilot.name} as drafts` : "Apply this workbook as drafts"}
        detail={`${pilot ? "Its clause versions and the precedent for its agreement type" : "New and changed clause versions"} become drafts, and playbooks are created unpublished. Drafts somebody wrote in the platform are never overwritten.${rows && leaveOut ? ` ${rows} rows with errors are left out.` : ""}`}
        confirmLabel="Apply"
        busy={apply.busy}
        error={apply.error?.message}
        onCancel={() => setConfirming(false)}
        onConfirm={() => void apply.run()}
      />
    </div>
  );
}

export function WorkbookImportScreen() {
  const [file, setFile] = React.useState<File | null>(null);
  const [problem, setProblem] = React.useState<string | null>(null);
  const [record, setRecord] = React.useState<WorkbookImport | null>(null);
  const [applied, setApplied] = React.useState<WorkbookImport | null>(null);
  const input = React.useRef<HTMLInputElement>(null);
  const history = useApi<WorkbookImport[]>("/library/imports", [record?.id, applied?.id]);

  const check = useAction(async () => {
    const found = workbookFileProblem(file);
    setProblem(found);
    if (found || !file) {
      input.current?.focus();
      return;
    }
    setApplied(null);
    setRecord(await upload<WorkbookImport>("/library/imports", file));
  });

  const open = useAction(async (id: string) => {
    setApplied(null);
    setRecord(await api<WorkbookImport>(`/library/imports/${id}`));
  });

  const serverProblem = check.error?.fieldErrors.file ?? check.error?.fieldErrors.content_type;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Check a workbook"
          subtitle="The legal team's Legal Playbook and Clause Library workbook. Checking writes nothing to the library."
        />
        <CardBody className="space-y-3">
          <Field label="Workbook" required hint={`An .xlsx file of at most ${MAX_UPLOAD_MB} MB.`} error={problem ?? serverProblem}>
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={input}
                type="file"
                accept=".xlsx"
                className="sr-only"
                aria-invalid={Boolean(problem ?? serverProblem)}
                onChange={(event) => {
                  const chosen = event.target.files?.[0] ?? null;
                  setFile(chosen);
                  setProblem(chosen ? workbookFileProblem(chosen) : null);
                }}
              />
              <Button size="sm" onClick={() => input.current?.click()}>
                Choose a workbook
              </Button>
              <span className="min-w-0 truncate text-sm text-muted-foreground">
                {file ? `${file.name}, ${Math.max(1, Math.round(file.size / 1024))} KB` : "Nothing chosen"}
              </span>
            </div>
          </Field>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary" disabled={check.busy} onClick={() => void check.run()}>
              {check.busy ? "Checking every row" : "Check the workbook"}
            </Button>
            {check.error && !serverProblem ? (
              <span className="text-sm text-destructive">{check.error.message}</span>
            ) : null}
          </div>
        </CardBody>
      </Card>

      {applied ? (
        <Notice tone="good" title="The workbook is in the library as drafts">
          {applied.message}{" "}
          {Object.entries(applied.written ?? {})
            .map(([key, count]) => `${count} ${key.replaceAll("_", " ")}`)
            .join(", ")}
          .{" "}
          <Link href="/workspace/library?tab=playbooks" className="underline underline-offset-2">
            Go to the playbooks to publish them
          </Link>
          .
        </Notice>
      ) : null}

      {record && !applied ? <CheckResult record={record} onApplied={setApplied} /> : null}

      <Card>
        <CardHeader title="Earlier checks" />
        <DataState
          loading={history.loading}
          errorMessage={history.error?.message}
          errorTitle="Earlier checks could not be loaded"
          isEmpty={!history.data?.length}
          emptyTitle="No workbook has been checked yet"
        >
          <Row cols="minmax(0,1fr) 10rem 8rem 8rem" head>
            <div>Workbook</div>
            <div>Checked</div>
            <div>Problems</div>
            <div>Status</div>
          </Row>
          {(history.data ?? []).map((item) => (
            <Row key={item.id} cols="minmax(0,1fr) 10rem 8rem 8rem">
              <button type="button" className="min-w-0 truncate text-left text-sm font-medium" onClick={() => void open.run(item.id)}>
                {item.filename}
              </button>
              <div className="text-xs">{formatDateTime(item.created_at)}</div>
              <div className={`text-xs ${item.errors ? "text-destructive" : ""}`}>
                {item.errors} {item.errors === 1 ? "error" : "errors"}, {item.warnings}{" "}
                {item.warnings === 1 ? "warning" : "warnings"}
              </div>
              <div>
                <Pill tone={item.status === "applied" || item.status === "piloted" ? "good" : item.errors ? "bad" : "neutral"}>
                  {titleCase(item.status)}
                </Pill>
              </div>
            </Row>
          ))}
        </DataState>
      </Card>
    </div>
  );
}

type ReviewPlaybook = { id: string; name: string; subtype: string; version: number };

export function useReviewPlaybooks(matterId: string | null | undefined) {
  const options = useApi<ReviewPlaybook[]>(matterId ? `/ai/review/${matterId}/playbooks` : null, [matterId]);
  const [chosen, setChosen] = React.useState("");
  React.useEffect(() => setChosen(""), [matterId]);
  const list = options.data ?? [];
  const needsChoice = list.length > 1;
  return {
    options: list,
    chosen,
    setChosen,
    needsChoice,
    playbookId: needsChoice ? chosen || undefined : undefined,
    missing: needsChoice && !chosen ? "Choose the playbook their paper is measured against." : null,
  };
}

export function ReviewPlaybookSelect({
  state,
  label = true,
}: Readonly<{ state: ReturnType<typeof useReviewPlaybooks>; label?: boolean }>) {
  if (!state.needsChoice) return null;
  const select = (
    <Select
      value={state.chosen}
      aria-label="Playbook"
      aria-invalid={Boolean(state.missing)}
      onChange={(event) => state.setChosen(event.target.value)}
    >
      <option value="">Choose the playbook</option>
      {state.options.map((option) => (
        <option key={option.id} value={option.id}>
          {option.name}
        </option>
      ))}
    </Select>
  );
  if (!label) return select;
  return (
    <Field
      label="Playbook"
      required
      hint="This agreement type has a playbook per sub-type. Choose the one this agreement is."
      error={state.missing}
    >
      {select}
    </Field>
  );
}
