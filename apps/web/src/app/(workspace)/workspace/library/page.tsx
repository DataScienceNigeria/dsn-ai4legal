"use client";

import Link from "next/link";
import * as React from "react";

import {
  AddTemplate,
  ClauseVersionList,
  NewClause,
  ProposeVersion,
} from "@/components/app/library-actions";
import { useRoles, useSession } from "@/components/app/session";
import {
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
  Spinner,
  Tabs,
} from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { Clause, Template } from "@/lib/types";
import { formatDate, titleCase } from "@/lib/utils";

const AUTHORITY_LABEL: Record<string, string> = {
  house: "Any authorised user on the matter",
  fallback_1: "Legal",
  fallback_2: "Legal lead",
  fallback_3: "Legal lead plus the accountable business owner",
  outside: "Legal lead plus the executive sponsor",
};

function ClauseTab({
  clauses,
  current,
  canPropose,
  onSelect,
}: Readonly<{
  clauses: ReturnType<typeof useApi<Clause[]>>;
  current: Clause | undefined;
  canPropose: boolean;
  onSelect: (category: string) => void;
}>) {
  return (
        <div className="grid gap-4 lg:gap-5 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <Card>
            <CardHeader
              title="Categories"
              actions={canPropose ? <NewClause onDone={() => clauses.reload()} /> : null}
            />
            <div className="max-h-[560px] overflow-y-auto">
              {clauses.loading ? (
                <Spinner />
              ) : (
                clauses.data?.map((clause) => (
                  <button
                    key={clause.id}
                    onClick={() => onSelect(clause.category)}
                    className={`block w-full border-b px-4 py-2.5 text-left last:border-b-0 hover:bg-muted/60 ${
                      current?.category === clause.category ? "bg-muted" : ""
                    }`}
                  >
                    <div className="text-sm font-medium">{clause.name}</div>
                    <Mono>{clause.current?.reference ?? clause.category}</Mono>
                  </button>
                ))
              )}
            </div>
          </Card>

          {current?.current ? (
            <div className="space-y-4">
              <Card>
                <CardHeader
                  title={current.name}
                  subtitle={
                    <span className="flex flex-wrap items-center gap-2">
                      <Mono>{current.current.reference}</Mono>
                      <Pill tone="good">{titleCase(current.current.status)}</Pill>
                      <span>Review due {formatDate(current.current.review_date)}</span>
                    </span>
                  }
                  actions={
                    canPropose ? (
                      <ProposeVersion
                        kind="clause"
                        code={current.category}
                        current={current.current}
                        onDone={() => clauses.reload()}
                      />
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        A change is proposed by legal staff and published by the clause owner
                      </span>
                    )
                  }
                />
                <CardBody className="space-y-4">
                  <div>
                    <div className="mb-1.5 flex items-center gap-2">
                      <span className="text-xs font-semibold text-muted-foreground">
                        HOUSE POSITION
                      </span>
                      <Pill tone="good">Presentable as house position</Pill>
                    </div>
                    <p className="rounded-md border border-brand/20 bg-brand/5 p-3 text-sm leading-relaxed">
                      {current.current.house_position}
                    </p>
                  </div>

                  <div>
                    <div className="mb-1.5 text-xs font-semibold text-muted-foreground">
                      RANKED FALLBACKS, WITH THE AUTHORITY NEEDED TO CONCEDE
                    </div>
                    <div className="space-y-2">
                      {current.current.fallbacks.map((fallback) => (
                        <div key={fallback.rank} className="rounded-md border p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <Pill tone="info">Fallback {fallback.rank}</Pill>
                            <span className="text-xs text-muted-foreground">
                              {AUTHORITY_LABEL[fallback.required_authority] ??
                                titleCase(fallback.required_authority)}
                            </span>
                          </div>
                          <p className="mt-1.5 text-sm leading-relaxed">{fallback.text}</p>
                          {fallback.conditions ? (
                            <p className="mt-1 text-xs text-muted-foreground">
                              Applies when: {fallback.conditions}
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>

                  {current.current.unacceptable_position ? (
                    <div>
                      <div className="mb-1.5 text-xs font-semibold text-muted-foreground">
                        UNACCEPTABLE
                      </div>
                      <p className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm leading-relaxed">
                        {current.current.unacceptable_position}
                      </p>
                    </div>
                  ) : null}
                </CardBody>
              </Card>

              <ClauseVersionList clause={current} onChanged={() => clauses.reload()} />
            </div>
          ) : (
            <Empty title="Choose a clause category" />
          )}
        </div>
  );
}

export default function Library() {
  const { entity } = useSession();
  const { has } = useRoles();
  const canPropose = has("counsel", "head_of_legal", "admin");
  const [tab, setTab] = React.useState("clauses");
  const [selected, setSelected] = React.useState<string | null>(null);

  const clauses = useApi<Clause[]>("/clauses", [entity]);
  const templates = useApi<Template[]>("/templates", [entity]);
  const reviews = useApi<
    { reference: string; kind: string; review_date: string; overdue: boolean }[]
  >("/library/review-due", [entity]);

  const current = clauses.data?.find((clause) => clause.category === selected) ?? clauses.data?.[0];

  if (clauses.error) {
    return <Refusal title="The clause library is not available to you" reason={clauses.error.message} />;
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="Templates and clauses"
        subtitle={
          "The single source of truth for house position. Only an approved, effective version " +
          "may be used for generation, and a superseded version stays readable."
        }
      />

      {reviews.data?.some((row) => row.overdue) ? (
        <Notice tone="warn" title="Some versions are past their review date">
          {reviews.data
            .filter((row) => row.overdue)
            .map((row) => row.reference)
            .join(", ")}
        </Notice>
      ) : null}

      <Tabs
        tabs={[
          { id: "clauses", label: "Clauses", badge: clauses.data?.length },
          { id: "templates", label: "Templates", badge: templates.data?.length },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "clauses" ? (
        <ClauseTab
          clauses={clauses}
          current={current}
          canPropose={canPropose}
          onSelect={setSelected}
        />
      ) : null}
      {tab === "templates" ? (
        <div className="space-y-4">
        <Card>
          <CardHeader
            title="Templates"
            subtitle="Only an approved, effective version may generate"
            actions={canPropose ? <AddTemplate onDone={() => templates.reload()} /> : null}
          />
          <div>
            <Row cols="minmax(0,1fr) 8.75rem 6.875rem 7.5rem 7.5rem" head>
              <div>Template</div>
              <div>Version</div>
              <div>Status</div>
              <div>Effective</div>
              <div>Review due</div>
            </Row>
            {templates.loading ? (
              <Spinner />
            ) : !templates.data?.length ? (
              <Empty title="No template applies to this entity" />
            ) : (
              templates.data.map((template) => (
                <Row key={template.id} cols="minmax(0,1fr) 8.75rem 6.875rem 7.5rem 7.5rem">
                  <div>
                    <Link
                      href={`/workspace/library/${template.code}`}
                      className="text-sm font-medium"
                    >
                      {template.name}
                    </Link>
                    <div className="text-xs text-muted-foreground">
                      {titleCase(template.agreement_type)}, {template.jurisdiction}
                    </div>
                  </div>
                  <Mono>{template.current?.reference ?? "No approved version"}</Mono>
                  <div>
                    <Pill tone={template.current ? "good" : "warn"}>
                      {template.current ? titleCase(template.current.status) : "Draft only"}
                    </Pill>
                  </div>
                  <div className="text-xs">{formatDate(template.current?.effective_date)}</div>
                  <div className="text-xs">{formatDate(template.current?.review_date)}</div>
                </Row>
              ))
            )}
          </div>
        </Card>

        </div>
      ) : null}

      <p className="text-xs leading-relaxed text-muted-foreground">
        Publication requires the clause-owner role and a fresh authentication, and it supersedes
        the previous version atomically. Legal staff may propose a change but cannot publish one alone.
      </p>
    </div>
  );
}
