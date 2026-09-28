"use client";

import * as React from "react";

import { useSession } from "@/components/app/session";
import { Button, Field, Input, Modal, Mono, Notice, Pill, Select } from "@/components/ui";
import { ApiError, api, postForm, upload } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { HistoricalFiled, HistoricalReading, Vocabulary } from "@/lib/types";

type Counterparty = { id: string; reference: string; legal_name: string };

type Row = {
  key: string;
  file: File;
  state: "reading" | "ready" | "filing" | "filed" | "failed";
  reading: HistoricalReading | null;
  counterparty: string;
  newName: string;
  agreementType: string;
  effective: string;
  end: string;
  error: string | null;
  filed: HistoricalFiled | null;
};

const NEW = "__new__";
const ACCEPT = ".pdf,.docx,.txt";

function size(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function message(error: unknown): string {
  if (error instanceof ApiError) {
    const details = Object.values(error.fieldErrors ?? {});
    return details.length ? `${error.message} ${details.join(" ")}` : error.message;
  }
  return "That did not work. Try again.";
}

function complete(row: Row): boolean {
  if (row.state !== "ready" || row.reading?.already_archived) return false;
  if (!row.counterparty) return false;
  return row.counterparty !== NEW || row.newName.trim().length >= 2;
}

/*
  Agreements signed before the platform existed, filed by the legal team one or
  many at a time.

  Each file is read before anything is stored, and what the reading suggests is
  shown beside where it came from so the person filing checks a quotation rather
  than trusting a guess. Nothing is chosen for them: the counterparty starts
  empty even where the filename looks like a match, because a wrong party on an
  immutable record is the one mistake here that cannot be put right quietly.

  The file is stored exactly as it arrives. Its text is read for search only.
*/
export function HistoricalImport({
  onClose,
  onFiled,
}: Readonly<{ onClose: () => void; onFiled: () => void }>) {
  const { me, entity: working } = useSession();
  const entities = me?.entities ?? [working];
  const [entity, setEntity] = React.useState(working);
  const [rows, setRows] = React.useState<Row[]>([]);
  const [running, setRunning] = React.useState(false);
  const [dragging, setDragging] = React.useState(false);
  const picker = React.useRef<HTMLInputElement>(null);

  const counterparties = useApi<Counterparty[]>("/counterparties");
  const vocabulary = useApi<Vocabulary>("/lifecycle/vocabulary");

  function patch(key: string, change: Partial<Row>) {
    setRows((previous) => previous.map((row) => (row.key === key ? { ...row, ...change } : row)));
  }

  async function add(files: FileList | File[]) {
    const fresh: Row[] = Array.from(files).map((file) => ({
      key: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2)}`,
      file,
      state: "reading",
      reading: null,
      counterparty: "",
      newName: "",
      agreementType: "",
      effective: "",
      end: "",
      error: null,
      filed: null,
    }));
    setRows((previous) => [...previous, ...fresh]);

    for (const row of fresh) {
      try {
        const reading = await upload<HistoricalReading>("/contracts/historical/read", row.file);
        patch(row.key, {
          state: "ready",
          reading,
          newName: reading.suggested.counterparty?.value ?? "",
          agreementType: reading.suggested.agreement_type?.value ?? "",
          effective: reading.suggested.effective_date?.value ?? "",
        });
      } catch (error) {
        patch(row.key, { state: "failed", error: message(error) });
      }
    }
  }

  async function fileAll() {
    setRunning(true);
    const created = new Map<string, string>();
    let filedAny = false;

    for (const row of rows.filter(complete)) {
      patch(row.key, { state: "filing", error: null });
      try {
        let counterpartyId = row.counterparty;
        if (counterpartyId === NEW) {
          const name = row.newName.trim();
          const known = created.get(name.toLowerCase());
          if (known) {
            counterpartyId = known;
          } else {
            const result = await api<{ created: Counterparty | null; message: string }>(
              "/counterparties",
              {
                method: "POST",
                body: JSON.stringify({ legal_name: name, confirm_despite_duplicates: true }),
              },
            );
            if (!result.created) throw new Error(result.message);
            counterpartyId = result.created.id;
            created.set(name.toLowerCase(), counterpartyId);
          }
        }

        const form = new FormData();
        form.append("file", row.file);
        form.append("entity", entity);
        form.append("counterparty_id", counterpartyId);
        if (row.agreementType) form.append("agreement_type", row.agreementType);
        if (row.effective) form.append("effective_date", row.effective);
        if (row.end) form.append("end_date", row.end);

        const filed = await postForm<HistoricalFiled>("/contracts/historical", form);
        patch(row.key, { state: "filed", filed });
        filedAny = true;
      } catch (error) {
        patch(row.key, {
          state: "ready",
          error: error instanceof Error && !(error instanceof ApiError) ? error.message : message(error),
        });
      }
    }

    setRunning(false);
    if (filedAny) {
      onFiled();
      void counterparties.reload();
    }
  }

  const ready = rows.filter(complete).length;
  const filed = rows.filter((row) => row.state === "filed").length;
  const waiting = rows.filter(
    (row) => row.state === "ready" && !row.reading?.already_archived && !complete(row),
  ).length;
  const types = vocabulary.data?.agreement_types ?? [];
  const everyone = counterparties.data ?? [];

  return (
    <Modal
      open
      width="lg"
      title="File agreements signed before the platform"
      subtitle="One file or many. Each is stored exactly as it arrives and read for search only."
      dismissible={!running}
      onClose={onClose}
      footer={
        <div className="flex w-full flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">
            {rows.length === 0
              ? "No files chosen yet"
              : `${filed} filed, ${ready} ready${waiting ? `, ${waiting} need a counterparty` : ""}`}
          </span>
          <div className="flex gap-2">
            <Button onClick={onClose} disabled={running}>
              {filed ? "Done" : "Cancel"}
            </Button>
            <Button variant="primary" disabled={running || ready === 0} onClick={() => void fileAll()}>
              {running ? "Filing" : ready === 1 ? "File 1 agreement" : `File ${ready} agreements`}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        {entities.length > 1 ? (
          <Field
            label="Which organisation signed these"
            hint="Decides who can see them. Choose before adding files, and file the other organisation's separately."
            required
          >
            <Select
              value={entity}
              disabled={running || rows.some((row) => row.state === "filed")}
              onChange={(event) => setEntity(event.target.value)}
            >
              {entities.map((code) => (
                <option key={code} value={code}>
                  {code === "DSN" ? "Data Science Nigeria" : code === "EAI" ? "EqualyzAI" : code}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}

        <input
          ref={picker}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(event) => {
            if (event.target.files?.length) void add(event.target.files);
            event.target.value = "";
          }}
        />
        <button
          type="button"
          disabled={running}
          onClick={() => picker.current?.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            if (event.dataTransfer.files.length) void add(event.dataTransfer.files);
          }}
          className={
            "w-full rounded-lg border-2 border-dashed p-6 text-center text-sm transition-colors " +
            (dragging ? "border-brand bg-brand/5" : "border-border hover:bg-muted/40")
          }
        >
          <div className="font-medium">Drop signed agreements here, or choose files</div>
          <div className="mt-1 text-xs text-muted-foreground">
            PDF, Word or text. A scan with no text layer is archived but cannot be searched.
          </div>
        </button>

        {rows.map((row) => (
          <FileRow
            key={row.key}
            row={row}
            types={types}
            everyone={everyone}
            running={running}
            onChange={(change) => patch(row.key, change)}
            onRemove={() => setRows((previous) => previous.filter((one) => one.key !== row.key))}
          />
        ))}

        {rows.length > 0 ? (
          <Notice title="What filing does">
            Each file is scanned, hashed and stored unchanged and immutable. It is recorded as signed
            before the platform, with no matter, approvals or signature record behind it, and its
            text is indexed so Memory can answer from it and cite the page.
          </Notice>
        ) : null}
      </div>
    </Modal>
  );
}

function Source({ suggested }: Readonly<{ suggested: { source: string } | null | undefined }>) {
  if (!suggested) return null;
  return <div className="mt-1 text-2xs text-muted-foreground">{`Suggested from ${suggested.source}`}</div>;
}

function FileRow({
  row,
  types,
  everyone,
  running,
  onChange,
  onRemove,
}: Readonly<{
  row: Row;
  types: { key: string; label: string }[];
  everyone: Counterparty[];
  running: boolean;
  onChange: (change: Partial<Row>) => void;
  onRemove: () => void;
}>) {
  const reading = row.reading;
  const locked = running || row.state === "filed" || row.state === "filing";
  const matches = reading?.counterparty_matches ?? [];
  const matchIds = new Set(matches.map((one) => one.id));

  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{row.file.name}</div>
          <div className="text-xs text-muted-foreground">{size(row.file.size)}</div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {row.state === "reading" ? <Pill tone="neutral">Reading</Pill> : null}
          {row.state === "filing" ? <Pill tone="neutral">Filing</Pill> : null}
          {row.state === "filed" && row.filed ? (
            <Pill tone="good">
              Filed as <Mono>{row.filed.reference}</Mono>
            </Pill>
          ) : null}
          {reading?.already_archived ? (
            <Pill tone="warn">
              Already filed as <Mono>{reading.already_archived}</Mono>
            </Pill>
          ) : null}
          {reading && !reading.already_archived && row.state !== "filed" ? (
            reading.readable ? (
              <Pill tone="good">Searchable</Pill>
            ) : (
              <Pill tone="warn">Archive only</Pill>
            )
          ) : null}
          {!locked ? (
            <Button size="sm" onClick={onRemove}>
              Remove
            </Button>
          ) : null}
        </div>
      </div>

      {row.error ? <p className="text-xs text-destructive">{row.error}</p> : null}
      {reading?.unreadable_reason && row.state !== "filed" ? (
        <p className="text-xs text-muted-foreground">{reading.unreadable_reason}</p>
      ) : null}
      {row.state === "filed" && row.filed ? (
        <p className="text-xs text-muted-foreground">
          {row.filed.searchable
            ? `Stored unchanged. ${row.filed.passages} passages can now be found in Memory.`
            : "Stored unchanged. Its text could not be read, so it will not appear in Memory."}
        </p>
      ) : null}

      {reading && !reading.already_archived && row.state !== "filed" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Who it is with" required>
            <Select
              value={row.counterparty}
              disabled={locked}
              onChange={(event) => onChange({ counterparty: event.target.value, error: null })}
            >
              <option value="">Choose the counterparty</option>
              {matches.length ? (
                <optgroup label="Looks like the filename">
                  {matches.map((one) => (
                    <option key={one.id} value={one.id}>
                      {`${one.legal_name}, ${one.reference}`}
                    </option>
                  ))}
                </optgroup>
              ) : null}
              <optgroup label="Everyone on record">
                {everyone
                  .filter((one) => !matchIds.has(one.id))
                  .map((one) => (
                    <option key={one.id} value={one.id}>
                      {`${one.legal_name}, ${one.reference}`}
                    </option>
                  ))}
              </optgroup>
              <option value={NEW}>Someone not on record yet</option>
            </Select>
            {row.counterparty === NEW ? (
              <div className="mt-2">
                <Input
                  value={row.newName}
                  disabled={locked}
                  placeholder="Their full legal name"
                  onChange={(event) => onChange({ newName: event.target.value })}
                />
                <Source suggested={reading.suggested.counterparty} />
              </div>
            ) : null}
          </Field>

          <Field label="Type of agreement" hint="Leave blank if it is not clear from the paper.">
            <Select
              value={row.agreementType}
              disabled={locked}
              onChange={(event) => onChange({ agreementType: event.target.value })}
            >
              <option value="">Not sure</option>
              {types.map((term) => (
                <option key={term.key} value={term.key}>
                  {term.label}
                </option>
              ))}
            </Select>
            <Source suggested={row.agreementType ? reading.suggested.agreement_type : null} />
          </Field>

          <Field label="Effective date">
            <Input
              type="date"
              value={row.effective}
              disabled={locked}
              onChange={(event) => onChange({ effective: event.target.value })}
            />
            <Source suggested={row.effective ? reading.suggested.effective_date : null} />
          </Field>

          <Field label="End date" hint="Leave blank if it has none or you do not know it.">
            <Input
              type="date"
              value={row.end}
              disabled={locked}
              onChange={(event) => onChange({ end: event.target.value })}
            />
          </Field>
        </div>
      ) : null}
    </div>
  );
}
