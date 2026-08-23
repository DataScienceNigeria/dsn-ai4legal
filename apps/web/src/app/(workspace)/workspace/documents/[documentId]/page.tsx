"use client";

import { useParams } from "next/navigation";
import * as React from "react";

import { useRoles, useSession } from "@/components/app/session";
import { ProvenancePill } from "@/components/app/status";
import { SuperDocEditor, type DocumentMode } from "@/components/app/superdoc-editor";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Empty,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Spinner,
} from "@/components/ui";
import { api, download } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { DocumentRecord } from "@/lib/types";
import { cn, formatDateTime, titleCase } from "@/lib/utils";

const MODES: { id: DocumentMode; label: string; detail: string }[] = [
  { id: "viewing", label: "Viewing", detail: "Read only, tracked changes shown" },
  { id: "suggesting", label: "Suggesting", detail: "Edits are recorded as tracked changes" },
  { id: "editing", label: "Editing", detail: "Direct edit, attributed to you" },
];

export default function DocumentScreen() {
  const { documentId } = useParams<{ documentId: string }>();
  const { me } = useSession();
  const [mode, setMode] = React.useState<DocumentMode>("suggesting");
  const [showEditor, setShowEditor] = React.useState(false);

  const { has } = useRoles();
  const { data, loading, error, reload } = useApi<DocumentRecord>(`/documents/${documentId}`);
  const [verified, setVerified] = React.useState<string | null>(null);

  const save = useAction(async (name: string) => {
    await download(`/documents/${documentId}/download`, `${name}.docx`);
  });

  /* The stored hash is recomputed from the record on the server. If the two
     disagree, the copy in front of you is not the copy that was approved. */
  const verify = useAction(async (expected: string) => {
    const result = await api<{ content_hash: string }>(`/documents/${documentId}/hash`);
    setVerified(
      result.content_hash === expected
        ? "The stored hash matches the record. This is the document that was approved."
        : `The hashes disagree. The record holds ${result.content_hash}.`,
    );
  });

  const redline = useAction(async () => {
    await api<{ message: string }>(`/documents/${documentId}/redline`, { method: "POST" });
    reload();
  });

  if (loading) return <Spinner />;
  if (error) return <Refusal title="That document was not found" reason={error.message} />;

  const document = data!;
  const failedChecks = document.consistency_checks.filter((check) => !check.passed);

  return (
    <div className="space-y-6">
      <PageTitle
        title={document.name}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <Pill tone={document.immutable ? "good" : "neutral"}>
              {titleCase(document.document_type)}
            </Pill>
            <span>Version {document.version}</span>
            <Mono>{document.content_hash.slice(0, 24)}</Mono>
            {document.template_version_ref ? <Mono>{document.template_version_ref}</Mono> : null}
            {document.novel_clause_count ? (
              <Pill tone="novel">{document.novel_clause_count} novel clauses</Pill>
            ) : (
              <Pill tone="good">Every clause traced to the approved library</Pill>
            )}
          </span>
        }
        actions={
          <>
            <Button variant={showEditor ? "default" : "primary"} onClick={() => setShowEditor((v) => !v)}>
              {showEditor ? "Close the editor" : "Open in the editor"}
            </Button>
            <Button disabled={save.busy} onClick={() => void save.run(document.name)}>
              Download
            </Button>
            <Button disabled={verify.busy} onClick={() => void verify.run(document.content_hash)}>
              Verify the hash
            </Button>
            {has("counsel", "head_of_legal", "admin") && !document.immutable ? (
              <Button disabled={redline.busy} onClick={() => void redline.run()}>
                Produce a redline
              </Button>
            ) : null}
          </>
        }
      />

      {verified ? <Notice tone="info" title="Hash check">{verified}</Notice> : null}
      {save.error ? <Refusal title="That download was refused" reason={save.error.message} /> : null}
      {verify.error ? <Refusal title="The hash could not be read" reason={verify.error.message} /> : null}
      {redline.error ? (
        <Refusal title="No redline was produced" reason={redline.error.message} reasons={redline.error.reasons} />
      ) : null}

      {document.immutable ? (
        <Notice tone="good" title="This is the authoritative executed copy">
          It is write-once for its retention period. A later upload is recorded as a linked
          amendment, never as a replacement.
        </Notice>
      ) : null}

      {failedChecks.length ? (
        <Refusal
          title="Deterministic checks did not all pass"
          reasons={failedChecks.flatMap((check) =>
            check.items.length
              ? check.items.map((item) => `${titleCase(check.name)}: ${item}`)
              : [`${titleCase(check.name)}: ${check.detail}`],
          )}
        />
      ) : (
        <Notice tone="good" title="Deterministic checks passed">
          Defined terms, cross-references, numbering, placeholders and date logic were all
          checked mechanically before this document was presented.
        </Notice>
      )}

      {showEditor ? (
        <Card>
          <CardHeader
            title="Document editor"
            subtitle="DOCX-native, with tracked changes. The platform copy stays authoritative."
            actions={
              <div className="flex rounded-md bg-muted p-0.5">
                {MODES.map((option) => (
                  <button
                    key={option.id}
                    title={option.detail}
                    onClick={() => setMode(option.id)}
                    className={cn(
                      "rounded-sm px-2.5 py-1 text-xs font-medium transition-colors",
                      mode === option.id
                        ? "bg-card text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            }
          />
          <CardBody>
            {document.immutable && mode !== "viewing" ? (
              <Notice tone="warn" title="An executed copy cannot be edited">
                Switch to viewing. To change what was signed, record an amendment against the
                contract instead.
              </Notice>
            ) : (
              <SuperDocEditor
                source={`/documents/${document.id}/download`}
                documentName={document.name}
                mode={document.immutable ? "viewing" : mode}
                user={{ name: me?.name ?? "Counsel", email: me?.email ?? "" }}
              />
            )}
          </CardBody>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader
            title="Clause provenance"
            subtitle="Where each clause came from. Novel text is marked wherever it appears."
          />
          <div>
            {!document.blocks.length ? (
              <Empty title="This record holds no assembled clauses" />
            ) : (
              document.blocks.map((block) => (
                <div key={block.key} className="border-b p-4 last:border-b-0">
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-sm font-semibold">
                      {block.number} {block.heading}
                    </div>
                    <ProvenancePill
                      provenance={block.provenance}
                      reference={block.source_reference}
                    />
                  </div>
                  <p
                    className={cn(
                      "mt-1.5 whitespace-pre-wrap text-sm leading-relaxed",
                      block.novel && "rounded-md border border-secondary/30 bg-secondary/5 p-2.5",
                    )}
                  >
                    {block.text}
                  </p>
                </div>
              ))
            )}
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Open items" subtitle="What the assembly could not resolve" />
            <CardBody>
              {document.open_items.length ? (
                <ul className="space-y-1.5 text-sm">
                  {document.open_items.map((item) => (
                    <li key={item} className="flex gap-2 leading-relaxed">
                      <span aria-hidden className="text-warning">&#9888;</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-sm text-muted-foreground">
                  Nothing outstanding was reported.
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Versions used" />
            <CardBody className="space-y-1.5">
              {document.template_version_ref ? (
                <div className="flex justify-between gap-2 text-sm">
                  <span className="text-muted-foreground">Template</span>
                  <Mono>{document.template_version_ref}</Mono>
                </div>
              ) : null}
              {document.clause_versions.map((reference) => (
                <div key={reference} className="flex justify-between gap-2 text-sm">
                  <span className="text-muted-foreground">Clause</span>
                  <Mono>{reference}</Mono>
                </div>
              ))}
              <div className="flex justify-between gap-2 pt-1.5 text-sm">
                <span className="text-muted-foreground">Generated</span>
                <span>{formatDateTime(document.generated_at)}</span>
              </div>
            </CardBody>
          </Card>

          <Notice title="Reproducibility">
            Regenerating from the same record and the same template version produces a
            byte-identical file and therefore the same hash. That is what makes this document
            attributable.
          </Notice>
        </div>
      </div>
    </div>
  );
}
