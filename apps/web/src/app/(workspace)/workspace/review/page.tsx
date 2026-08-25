"use client";

import * as React from "react";

import { useRoles, useSession } from "@/components/app/session";
import { DecisionPill, SeverityPill } from "@/components/app/status";
import { SuperDocEditor } from "@/components/app/superdoc-editor";
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
  Row,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api, download, upload } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { DocumentRecord, Finding, Matter, RoundSummary } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

const AUTHORITY_LABEL: Record<string, string> = {
  house: "Any authorised user",
  fallback_1: "Legal",
  fallback_2: "Legal lead",
  fallback_3: "Legal lead plus the accountable business owner",
  outside: "Legal lead plus the executive sponsor",
};

/*
  Their paper, against our playbook.

  Two ways to work it, because two different things happen here.

  Reading is one: findings one after another, severity and authority visible,
  deciding what the house will and will not concede. It is also the only mode
  that makes sense when the negotiation is happening in somebody else's Google
  Docs and the copy here is just a copy.

  Editing is the other, and it is what the screen was missing. A reviewer read
  a complaint about clause 9, went somewhere else to make the change, and came
  back to tick a box. Their document now sits beside the findings and the
  change is typed into it here.

  Nothing on this screen writes into their paper on the reader's behalf. The
  platform suggests, says which clause it is about, and records what was
  decided; the wording that goes in is typed by the person accountable for it.
  One writer, so the document and the record of who changed it cannot drift
  apart.
*/
export default function Review() {
  const { entity, me } = useSession();
  const { has } = useRoles();
  const matters = useApi<Matter[]>("/matters", [entity]);
  const [matterId, setMatterId] = React.useState<string>("");
  const [mode, setMode] = React.useState<"list" | "editor">("list");

  const inReview = React.useMemo(
    () =>
      (matters.data ?? []).filter((matter) => ["in_review", "escalated"].includes(matter.status)),
    [matters.data],
  );

  const active = matterId || inReview[0]?.id || "";
  const findings = useApi<Finding[]>(active ? `/matters/${active}/findings` : null, [active]);
  const rounds = useApi<RoundSummary[]>(active ? `/matters/${active}/review-rounds` : null, [
    active,
  ]);
  const documents = useApi<DocumentRecord[]>(active ? `/matters/${active}/documents` : null, [
    active,
  ]);
  const [selected, setSelected] = React.useState<string | null>(null);

  const all = React.useMemo(() => findings.data ?? [], [findings.data]);
  const current = all.find((finding) => finding.id === selected) ?? all[0] ?? null;

  /*
    Their latest paper, which is what a later round is raised against and what
    the editor opens. A superseded version is what an older round described,
    and editing that would fork the draft.
  */
  const paper = React.useMemo(() => {
    const theirs = (documents.data ?? []).filter(
      (document) => document.document_type === "counterparty",
    );
    return [...theirs].sort((left, right) => right.version - left.version)[0] ?? null;
  }, [documents.data]);

  /*
    The suggestion is a draft, so it is editable before it is accepted. The
    draft starts from whatever the record holds: an edit already recorded on
    the finding, otherwise the model's wording.
  */
  const [draft, setDraft] = React.useState("");
  const [editing, setEditing] = React.useState(false);
  const suggestion = current?.suggested_redline ?? "";

  React.useEffect(() => {
    setDraft(current?.edited_text ?? current?.suggested_redline ?? "");
    setEditing(false);
  }, [current?.id, current?.edited_text, current?.suggested_redline]);

  const edited = draft.trim() !== suggestion.trim() && draft.trim().length > 0;

  /*
    Authority to concede, PRD section 14.3. Legal staff hold house position and
    fallback 1; the legal lead holds everything above.

    The approval chain would catch a concession made above someone's level, but
    it would catch it as a yes or no on a whole agreement. This is what makes a
    concession surface as a concession, and what the decision record is written
    from.
  */
  function authorised(finding: Finding): boolean {
    if (has("head_of_legal", "admin")) return true;
    if (has("counsel")) {
      return (
        finding.required_authority !== "fallback_2" &&
        finding.required_authority !== "fallback_3" &&
        finding.required_authority !== "outside"
      );
    }
    return false;
  }

  const decide = useAction(async (findingId: string, decision: string, editedText?: string) => {
    await api(`/findings/${findingId}/decision`, {
      method: "POST",
      body: { decision, edited_text: editedText ?? null },
    });
    findings.reload();
  });

  /*
    Saving what was typed. Every save is a new version of their paper, because
    the version it replaces is what a round of findings was raised against, and
    rewriting that would leave those findings describing a document that no
    longer exists.
  */
  const save = React.useCallback(
    async (blob: Blob) => {
      if (!paper) return;
      await upload(
        `/documents/${paper.id}/source`,
        new File([blob], paper.name, { type: DOCX }),
        "PUT",
      );
      documents.reload();
    },
    // documents.reload is stable for the life of the query, and depending on
    // the whole object would rebuild this on every poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [paper?.id, paper?.name],
  );

  /*
    Their paper back with our findings in the margin, in the format Word,
    Pages and Google Docs all read. This is the answer to a negotiation that
    happens where the platform cannot see: send the findings out, and read the
    returned file to find out what was settled.
  */
  const send = useAction(async () => {
    await download(
      `/matters/${active}/findings/export`,
      `${matters.data?.find((m) => m.id === active)?.number ?? "review"}-marked-up.docx`,
    );
  });

  const rereview = useAction(async () => {
    if (!paper) return;
    await api(`/ai/review/${active}?document_id=${paper.id}`, { method: "POST" });
    findings.reload();
    rounds.reload();
  });

  const decided = all.filter((finding) => finding.decision !== "pending").length;
  const latest = rounds.data?.[rounds.data.length - 1] ?? null;
  const canEdit = has("counsel", "head_of_legal", "admin");

  return (
    <div className="space-y-6">
      <PageTitle
        title="Their paper, against our playbook"
        subtitle={
          "Findings cover both altered terms and required clauses that are absent. Every " +
          "suggestion is a draft until a named person accepts it, and every change to their " +
          "document is typed by a person."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Select value={active} onChange={(event) => setMatterId(event.target.value)}>
              {inReview.length === 0 ? <option value="">No matter is in review</option> : null}
              {inReview.map((matter) => (
                <option key={matter.id} value={matter.id}>
                  {matter.number}, {matter.title}
                </option>
              ))}
            </Select>
            {paper && canEdit ? (
              <>
                <Button
                  variant={mode === "editor" ? "default" : "primary"}
                  onClick={() => setMode(mode === "editor" ? "list" : "editor")}
                >
                  {mode === "editor" ? "Back to the list" : "Open the paper in the editor"}
                </Button>
                <Button disabled={send.busy} onClick={() => void send.run()}>
                  Send it out marked up
                </Button>
              </>
            ) : null}
          </div>
        }
      />

      {/*
        What each pass over their paper changed. The last figure is the point of
        rounds: something raised for the first time in a later round is what the
        counterparty altered while the argument was about a different clause,
        and no checklist finds it.
      */}
      {rounds.data && rounds.data.length > 1 ? (
        <Card>
          <CardHeader
            title={`Round ${latest?.round} of ${latest?.document_name ?? "their paper"}`}
            subtitle="Settled by what their returned draft no longer says, not by anyone ticking it off."
          />
          <CardBody className="flex flex-wrap gap-x-10 gap-y-3">
            <Figure label="Settled since the last round" value={latest?.settled ?? 0} tone="good" />
            <Figure label="Still open" value={latest?.still_open ?? 0} tone="warn" />
            <Figure
              label="New, nobody asked for it"
              value={latest?.newly_raised ?? 0}
              tone={latest?.newly_raised ? "bad" : "muted"}
            />
          </CardBody>
        </Card>
      ) : null}

      {send.error ? (
        <Refusal title="That export was refused" reason={send.error.message} />
      ) : null}

      {rereview.error ? (
        <Refusal
          title="Their paper could not be re-read"
          reason={rereview.error.message}
          reasons={rereview.error.reasons}
        />
      ) : null}

      {!active ? (
        <Empty
          title="Nothing is under review"
          detail="Upload counterparty paper on a matter and run the comparison to populate this screen."
        />
      ) : findings.loading ? (
        <Spinner />
      ) : findings.error ? (
        <Refusal title="Findings are not available" reason={findings.error.message} />
      ) : !all.length ? (
        <Empty
          title="No findings on this matter"
          detail="Severity ranking needs a published playbook for the agreement type."
        />
      ) : (
        <div
          className={cn(
            "grid gap-4 lg:gap-5",
            mode === "editor"
              ? "lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]"
              : "lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]",
          )}
        >
          {mode === "editor" && paper ? (
            <Card className="overflow-hidden">
              <CardHeader
                title={paper.name}
                subtitle={`Version ${paper.version}. Every save is a new version, so the draft a round was raised against stays as it was.`}
                actions={
                  <Button size="sm" disabled={rereview.busy} onClick={() => void rereview.run()}>
                    Re-read it
                  </Button>
                }
              />
              <CardBody className="p-0">
                <SuperDocEditor
                  source={`/documents/${paper.id}/download`}
                  documentName={paper.name}
                  mode="editing"
                  exportable={false}
                  onAutosave={save}
                  user={{ name: me?.name ?? "Legal", email: me?.email ?? "" }}
                  height="min(calc(100vh - 24rem), 68vh)"
                />
              </CardBody>
            </Card>
          ) : (
            <Card>
              <CardHeader
                title={`${all.length} findings`}
                subtitle={`${decided} decided, ${all.length - decided} open`}
              />
              <div>
                <Row cols="minmax(0,1fr) 6.25rem 5.625rem" head>
                  <div>Finding</div>
                  <div>Severity</div>
                  <div>State</div>
                </Row>
                {all.map((finding) => (
                  <button
                    key={finding.id}
                    onClick={() => setSelected(finding.id)}
                    className={cn(
                      "block w-full text-left",
                      current?.id === finding.id &&
                        "bg-brand/5 shadow-[inset_2px_0_0] shadow-brand",
                    )}
                  >
                    <Row cols="minmax(0,1fr) 6.25rem 5.625rem">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">{finding.title}</div>
                        <div className="truncate text-xs text-muted-foreground">
                          {finding.clause_absent
                            ? "Required, not present"
                            : finding.their_reference}
                          {finding.carried_from_id ? " · still open from the last round" : ""}
                        </div>
                      </div>
                      <div>
                        <SeverityPill severity={finding.severity} />
                      </div>
                      <div>
                        <DecisionPill decision={finding.decision} />
                      </div>
                    </Row>
                  </button>
                ))}
              </div>
            </Card>
          )}

          <div className="space-y-4">
            {/*
              In the editor the findings are the side panel, so a way to move
              between them has to come with it. A reviewer working clause by
              clause should never leave the document to reach the next point.
            */}
            {mode === "editor" ? (
              <Card>
                <CardHeader
                  title={`${all.length} findings`}
                  subtitle={`${decided} decided, ${all.length - decided} open`}
                />
                <CardBody className="flex flex-wrap gap-1.5">
                  {all.map((finding, index) => (
                    <button
                      key={finding.id}
                      type="button"
                      onClick={() => setSelected(finding.id)}
                      title={finding.title}
                      className={cn(
                        "h-7 min-w-[1.75rem] rounded-md border px-2 text-xs font-medium transition-colors",
                        current?.id === finding.id
                          ? "border-brand bg-brand text-brand-foreground"
                          : finding.decision !== "pending"
                            ? "border-transparent bg-muted text-muted-foreground"
                            : "hover:bg-muted",
                      )}
                    >
                      {index + 1}
                    </button>
                  ))}
                </CardBody>
              </Card>
            ) : null}

            {current ? (
              <>
                <Card>
                  <CardHeader
                    title={current.title}
                    subtitle={
                      <span className="flex flex-wrap items-center gap-2">
                        <SeverityPill severity={current.severity} />
                        {current.clause_version_ref ? (
                          <Mono>{current.clause_version_ref}</Mono>
                        ) : null}
                        <Pill tone={current.matches_preapproved_fallback ? "good" : "warn"}>
                          {AUTHORITY_LABEL[current.required_authority] ??
                            titleCase(current.required_authority)}
                        </Pill>
                      </span>
                    }
                  />
                  <CardBody className="space-y-4">
                    {current.clause_absent ? (
                      <Notice tone="bad" title="This clause is absent altogether">
                        The playbook requires it for this agreement type and the draft does not
                        contain it. Missing protections are reported, not only altered ones.
                      </Notice>
                    ) : null}

                    {current.carried_from_id ? (
                      <Notice tone="warn" title="Still open from the last round">
                        Their returned draft still carries this point. It is one argument, not a
                        new complaint.
                      </Notice>
                    ) : null}

                    <div>
                      <div className="mb-1.5 flex flex-wrap items-center gap-2">
                        <span className="text-xs font-semibold text-muted-foreground">
                          THEIR TEXT
                        </span>
                        {current.their_reference ? <Mono>{current.their_reference}</Mono> : null}
                      </div>
                      <p className="rounded-md border border-destructive/25 bg-destructive/5 p-3 text-sm leading-relaxed">
                        {current.their_text ?? "Nothing in the draft addresses this point."}
                      </p>
                    </div>

                    <div>
                      <div className="mb-1.5 text-xs font-semibold text-muted-foreground">
                        OUR HOUSE POSITION
                      </div>
                      <p className="rounded-md border border-brand/25 bg-brand/5 p-3 text-sm leading-relaxed">
                        {current.house_position}
                      </p>
                    </div>

                    <div>
                      <div className="mb-1.5 flex flex-wrap items-center gap-2">
                        <span className="text-xs font-semibold text-muted-foreground">
                          SUGGESTED RESPONSE
                        </span>
                        <Pill tone={edited ? "info" : "novel"}>
                          {edited ? "Your wording" : "Draft until accepted"}
                        </Pill>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="ml-auto"
                          onClick={() => setEditing((open) => !open)}
                        >
                          {editing ? "Stop editing" : "Edit the wording"}
                        </Button>
                      </div>
                      {editing ? (
                        <>
                          <Textarea
                            value={draft}
                            onChange={(event) => setDraft(event.target.value)}
                            className="min-h-[9rem] leading-relaxed"
                            aria-label="Suggested response"
                          />
                          <div className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                            <span>
                              {edited
                                ? "Changed from the suggestion. Accepting records your wording, attributed to you."
                                : "Unchanged from the suggestion."}
                            </span>
                            {edited ? (
                              <button
                                type="button"
                                className="underline underline-offset-2 hover:text-foreground"
                                onClick={() => setDraft(suggestion)}
                              >
                                Restore the suggestion
                              </button>
                            ) : null}
                          </div>
                        </>
                      ) : (
                        <p className="whitespace-pre-wrap rounded-md border p-3 text-sm leading-relaxed">
                          {draft || suggestion}
                        </p>
                      )}
                    </div>

                    {current.clearance_rule ? (
                      <Notice tone="good" title="Cleared by rule">
                        {current.clearance_rule}
                      </Notice>
                    ) : null}

                    {decide.error ? (
                      <Refusal title="That decision was refused" reason={decide.error.message} />
                    ) : null}
                  </CardBody>
                </Card>

                {authorised(current) ? (
                  <div className="flex flex-wrap items-center gap-2">
                    {edited ? (
                      <Button
                        variant="primary"
                        disabled={decide.busy}
                        onClick={() => void decide.run(current.id, "edited", draft)}
                      >
                        Accept with my edit
                      </Button>
                    ) : (
                      <Button
                        variant="primary"
                        disabled={decide.busy}
                        onClick={() => void decide.run(current.id, "accepted")}
                      >
                        Accept the suggestion
                      </Button>
                    )}
                    <Button
                      variant="destructive"
                      disabled={decide.busy}
                      onClick={() => void decide.run(current.id, "rejected")}
                    >
                      Reject
                    </Button>
                    <span className="text-xs text-muted-foreground sm:ml-auto">
                      {mode === "editor"
                        ? "Accepting records the concession. The wording goes into the document beside this."
                        : "Accepted changes are attributed to you, not to the model."}
                    </span>
                  </div>
                ) : (
                  <Notice tone="warn" title="This concession is above your authority">
                    {`Conceding it needs ${
                      AUTHORITY_LABEL[current.required_authority] ??
                      titleCase(current.required_authority)
                    }. Escalate it rather than clearing it here.`}
                  </Notice>
                )}
              </>
            ) : null}
          </div>
        </div>
      )}

      {/*
        Where the round ends, and the answer to work that happened somewhere
        else. Nobody is asked to tick off what was settled in a fortnight of
        somebody's Google Docs: the returned paper is read again, and what it
        no longer says is what was conceded.
      */}
      {mode === "list" && paper && canEdit && all.length && decided === all.length ? (
        <Notice tone="info" title="Every finding on this round is decided">
          The changes go into their paper by hand, here or wherever the negotiation is happening.
          When their draft comes back, upload it and re-read it: what it no longer says is settled,
          what it still says is open, and anything new is what they changed while nobody was
          looking.
          <div className="mt-2.5 flex flex-wrap gap-2">
            <Button size="sm" variant="primary" disabled={send.busy} onClick={() => void send.run()}>
              Send it out marked up
            </Button>
            <Button size="sm" disabled={rereview.busy} onClick={() => void rereview.run()}>
              Re-read their paper
            </Button>
          </div>
        </Notice>
      ) : null}
    </div>
  );
}

function Figure({
  label,
  value,
  tone,
}: Readonly<{ label: string; value: number; tone: "good" | "warn" | "bad" | "muted" }>) {
  return (
    <div>
      <div
        className={cn(
          "text-2xl font-semibold tabular-nums",
          tone === "good" && "text-primary",
          tone === "warn" && "text-warning-foreground dark:text-warning",
          tone === "bad" && "text-destructive",
          tone === "muted" && "text-muted-foreground",
        )}
      >
        {value}
      </div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
