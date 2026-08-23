"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { Icon } from "@/components/app/icons";
import {
  CandidateReview,
  PlaybookView,
  ProposeVersion,
  VersionDecision,
} from "@/components/app/library-actions";
import { useRoles, useSession } from "@/components/app/session";
import { SuperDocEditor } from "@/components/app/superdoc-editor";
import {
  Button,
  Card,
  CardBody,
  Empty,
  Field,
  Modal,
  Mono,
  PageTitle,
  Pill,
  Refusal,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api, download, upload } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Template, TemplateVersion } from "@/lib/types";
import { formatDate, titleCase } from "@/lib/utils";

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

/*
  A template is read and edited on its own page rather than in a dialog. A
  dialog gives a document a few hundred pixels between two scrollbars, which is
  no way to read an agreement, and it puts the reader one stray click from
  losing their place.
*/
/*
  An approved version is never edited in place, so editing needs a draft. Where
  there is none this makes one from the version in force, rather than greying
  the button out and leaving the reader to discover that "propose a change" was
  the way in. The reason is still demanded and the draft still has to be
  published, so nothing is skipped.
*/
function editLabel(editing: boolean, hasDraft: boolean): string {
  if (editing) return "Done editing";
  return hasDraft ? "Edit the draft" : "Edit, as a new draft";
}

function TemplateHeader({
  template,
  version,
  code,
  editing,
  draft,
  mayEdit,
  canPropose,
  canExtract,
  onToggleMode,
  onExtract,
  onChanged,
}: Readonly<{
  template: Template;
  version: TemplateVersion | undefined;
  code: string;
  editing: boolean;
  draft: TemplateVersion | undefined;
  mayEdit: boolean;
  canPropose: boolean;
  canExtract: boolean;
  onToggleMode: () => void;
  onExtract: () => void;
  onChanged: () => void;
}>) {
  return (
    <PageTitle
      title={template.name}
      subtitle={
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <Mono className="whitespace-nowrap">{version?.reference ?? "No version"}</Mono>
          {editing ? (
            <Pill tone="warn">Editing the draft, saved as you type</Pill>
          ) : (
            <Pill tone={template.current ? "good" : "warn"}>
              {template.current
                ? `${titleCase(template.current.status)}, in use`
                : "Draft only, nothing generates yet"}
            </Pill>
          )}
          <span>{titleCase(template.agreement_type)}</span>
          <span>{template.jurisdiction}</span>
          {template.current?.effective_date ? (
            <span>Effective {formatDate(template.current.effective_date)}</span>
          ) : null}
        </span>
      }
      actions={
        <>
          <Link href="/workspace/library" className="no-underline">
            <Button size="sm">Back</Button>
          </Link>
          {/* One control, two states. Two buttons for two modes spent a whole
              row of the page saying which of them was already obvious from the
              document being editable or not. */}
          <Button
            size="sm"
            variant={editing ? "dark" : "primary"}
            disabled={!mayEdit}
            onClick={onToggleMode}
            title={mayEdit ? undefined : "Editing a template needs counsel or the Head of Legal."}
          >
            <Icon name={editing ? "templates" : "rename"} className="h-4 w-4" />
            {editLabel(editing, Boolean(draft))}
          </Button>
          <PlaybookView agreementType={template.agreement_type} />
          <Button
            size="sm"
            onClick={() => void download(`/templates/${code}/preview`, `${code}.docx`)}
          >
            <Icon name="archive" className="h-4 w-4" />
            Save as .docx
          </Button>
          {canExtract ? (
            <Button size="sm" onClick={onExtract}>
              <Icon name="templates" className="h-4 w-4" />
              Extract clauses
            </Button>
          ) : null}
          {canPropose ? (
            <ProposeVersion kind="template" code={code} current={null} onDone={onChanged} />
          ) : null}
          {/* A draft is only worth writing if it can be put into force from
              here. Publishing needs the Head of Legal and a fresh sign-in;
              the control renders nothing for anyone else. */}
          {draft ? (
            <VersionDecision reference={draft.reference} status={draft.status} onDone={onChanged} />
          ) : null}
        </>
      }
    />
  );
}

function StartDraftDialog({
  open,
  inForce,
  reason,
  busy,
  error,
  onReason,
  onCancel,
  onConfirm,
}: Readonly<{
  open: boolean;
  inForce: string | null;
  reason: string;
  busy: boolean;
  error: string | null;
  onReason: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}>) {
  return (
    <Modal
      open={open}
      title="Edit as a new draft"
      subtitle={`${inForce ?? "The version in force"} is approved, and an approved version is what documents were generated from. Editing starts a new draft from it, which supersedes it only once published.`}
      width="sm"
      onClose={onCancel}
      footer={
        <>
          <Button onClick={onCancel}>Cancel</Button>
          <Button variant="primary" disabled={!reason.trim() || busy} onClick={onConfirm}>
            {busy ? "Creating the draft" : "Create it and edit"}
          </Button>
        </>
      }
    >
      {error ? <Refusal title="That draft was not created" reason={error} /> : null}
      <Field label="What are you changing, and why" required>
        <Textarea value={reason} onChange={(event) => onReason(event.target.value)} />
      </Field>
    </Modal>
  );
}

export default function TemplatePage() {
  const { code } = useParams<{ code: string }>();
  const router = useRouter();
  const params = useSearchParams();
  const { me } = useSession();
  const { has } = useRoles();

  const template = useApi<Template>(`/templates/${code}`, [code]);
  const data = template.data;
  const draft = (data?.versions ?? []).find((version) => version.status === "draft");
  const mayEdit = has("counsel", "head_of_legal", "admin");

  const editing = params.get("mode") === "edit" && mayEdit && Boolean(draft);
  const [extracting, setExtracting] = React.useState(false);
  const [opening, setOpening] = React.useState(false);
  const [reason, setReason] = React.useState("");

  /*
    An approved version is never edited in place, so editing needs a draft.
    Rather than greying the button out and leaving the reader to discover that
    "Propose a change" is the way in, the button opens the draft when there is
    one and creates it when there is not. The reason is still demanded, and the
    new draft still has to be published, so nothing is skipped.
  */
  const startDraft = useAction(async () => {
    await api(`/templates/${code}/versions`, {
      method: "POST",
      body: { change_summary: reason.trim() },
    });
    template.reload();
    setOpening(false);
    setReason("");
    router.replace(`/workspace/library/${code}?mode=edit`);
  });

  const save = React.useCallback(
    async (blob: Blob) => {
      await upload(
        `/templates/${code}/source`,
        new File([blob], `${code}.docx`, { type: DOCX }),
        "PUT",
      );
    },
    [code],
  );

  function setMode(mode: "read" | "edit") {
    router.replace(mode === "edit" ? `/workspace/library/${code}?mode=edit` : `/workspace/library/${code}`);
  }

  if (template.loading) return <Spinner label="Opening the template" />;
  if (template.error || !data) {
    return <Empty title="That template was not found" detail={template.error?.message} />;
  }

  const version = editing ? draft : (data.current ?? draft);

  return (
    <div className="space-y-3">
      <TemplateHeader
        template={data}
        version={version}
        code={code}
        editing={editing}
        draft={draft}
        mayEdit={mayEdit}
        onToggleMode={() => {
          if (editing) setMode("read");
          else if (draft) setMode("edit");
          else setOpening(true);
        }}
        canPropose={mayEdit}
        canExtract={Boolean(draft?.import_id) && has("head_of_legal", "admin")}
        onExtract={() => setExtracting(true)}
        onChanged={() => template.reload()}
      />

      <StartDraftDialog
        open={opening}
        inForce={data.current?.reference ?? null}
        reason={reason}
        busy={startDraft.busy}
        error={startDraft.error?.message ?? null}
        onReason={setReason}
        onCancel={() => setOpening(false)}
        onConfirm={() => void startDraft.run()}
      />

      {extracting && draft?.import_id ? (
        <CandidateReview
          importId={draft.import_id}
          onDone={() => template.reload()}
          onClose={() => setExtracting(false)}
        />
      ) : null}

      <Card className="overflow-hidden">
        <CardBody className="p-0">
          <SuperDocEditor
            key={editing ? "edit" : "read"}
            source={
              editing
                ? `/templates/${code}/preview?version=${draft?.reference ?? ""}`
                : `/templates/${code}/preview`
            }
            documentName={data.name}
            mode={editing ? "editing" : "viewing"}
            exportable={false}
            onAutosave={editing ? save : undefined}
            user={{ name: me?.name ?? "Counsel", email: me?.email ?? "" }}
            height="min(calc(100vh - 15rem), 80vh)"
          />
        </CardBody>
      </Card>
    </div>
  );
}
