"use client";

import * as React from "react";

import { useRoles, useSession } from "@/components/app/session";
import { DecisionPill, SeverityPill } from "@/components/app/status";
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
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Finding, Matter } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

const AUTHORITY_LABEL: Record<string, string> = {
  house: "Any authorised user",
  fallback_1: "Counsel",
  fallback_2: "Head of Legal",
  fallback_3: "Head of Legal plus the accountable business owner",
  outside: "Head of Legal plus the executive sponsor",
};

export default function Review() {
  const { entity } = useSession();
  const { has } = useRoles();
  const matters = useApi<Matter[]>("/matters", [entity]);
  const [matterId, setMatterId] = React.useState<string>("");

  const inReview = React.useMemo(
    () => (matters.data ?? []).filter((matter) => ["in_review", "escalated"].includes(matter.status)),
    [matters.data],
  );

  const active = matterId || inReview[0]?.id || "";
  const findings = useApi<Finding[]>(active ? `/matters/${active}/findings` : null, [active]);
  const [selected, setSelected] = React.useState<string | null>(null);

  const current =
    findings.data?.find((finding) => finding.id === selected) ?? findings.data?.[0] ?? null;

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
    Authority to concede, PRD section 14.3. Legal operations may clear a minor
    finding that already matches a pre-approved fallback and nothing else.
  */
  function authorised(finding: Finding): boolean {
    if (has("head_of_legal", "admin")) return true;
    if (has("counsel")) {
      return finding.required_authority !== "fallback_2" &&
        finding.required_authority !== "fallback_3" &&
        finding.required_authority !== "outside";
    }
    if (has("legal_ops")) {
      return finding.severity === "minor" && finding.matches_preapproved_fallback;
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

  const decided = (findings.data ?? []).filter((finding) => finding.decision !== "pending").length;

  return (
    <div className="space-y-6">
      <PageTitle
        title="Their paper, against our playbook"
        subtitle={
          "Findings cover both altered terms and required clauses that are absent. Every " +
          "suggestion is a draft until a named person accepts it."
        }
        actions={
          <Select value={active} onChange={(event) => setMatterId(event.target.value)}>
            {inReview.length === 0 ? <option value="">No matter is in review</option> : null}
            {inReview.map((matter) => (
              <option key={matter.id} value={matter.id}>
                {matter.number}, {matter.title}
              </option>
            ))}
          </Select>
        }
      />

      {!active ? (
        <Empty
          title="Nothing is under review"
          detail="Upload counterparty paper on a matter and run the comparison to populate this screen."
        />
      ) : findings.loading ? (
        <Spinner />
      ) : findings.error ? (
        <Refusal title="Findings are not available" reason={findings.error.message} />
      ) : !findings.data?.length ? (
        <Empty
          title="No findings on this matter"
          detail="Severity ranking needs a published playbook for the agreement type."
        />
      ) : (
        <div className="grid gap-4 lg:gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
          <Card>
            <CardHeader
              title={`${findings.data.length} findings`}
              subtitle={`${decided} decided, ${findings.data.length - decided} open`}
            />
            <div>
              <Row cols="minmax(0,1fr) 6.25rem 5.625rem" head>
                <div>Finding</div>
                <div>Severity</div>
                <div>State</div>
              </Row>
              {findings.data.map((finding) => (
                <button
                  key={finding.id}
                  onClick={() => setSelected(finding.id)}
                  className={cn(
                    "block w-full text-left",
                    current?.id === finding.id && "bg-brand/5 shadow-[inset_2px_0_0] shadow-brand",
                  )}
                >
                  <Row cols="minmax(0,1fr) 6.25rem 5.625rem">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{finding.title}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        {finding.clause_absent ? "Required, not present" : finding.their_reference}
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

          {current ? (
            <div className="space-y-4">
              <Card>
                <CardHeader
                  title={current.title}
                  subtitle={
                    <span className="flex flex-wrap items-center gap-2">
                      <SeverityPill severity={current.severity} />
                      {current.clause_version_ref ? <Mono>{current.clause_version_ref}</Mono> : null}
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

                  <div>
                    <div className="mb-1.5 text-xs font-semibold text-muted-foreground">
                      THEIR TEXT
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
                    {edited
                      ? "Your wording is recorded as the accepted text, attributed to you."
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
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
