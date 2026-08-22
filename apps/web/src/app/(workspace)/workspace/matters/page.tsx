"use client";

import Link from "next/link";
import * as React from "react";

import { useSession } from "@/components/app/session";
import { SlaPill, StatusPill, TierPill } from "@/components/app/status";
import { Button, Card, CardHeader, Empty, PageTitle, Row, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { Matter } from "@/lib/types";

const FILTERS = [
  { id: "all", label: "All open" },
  { id: "mine", label: "Mine" },
  { id: "breach", label: "Past target" },
  { id: "waiting", label: "Waiting on someone" },
];

export default function Matters() {
  const { entity, me } = useSession();
  const [filter, setFilter] = React.useState("all");
  const { data, loading, error } = useApi<Matter[]>("/matters", [entity]);

  const rows = React.useMemo(() => {
    const all = data ?? [];
    if (filter === "mine") return all.filter((m) => m.responsible_lawyer_id === me?.id);
    if (filter === "breach") return all.filter((m) => m.sla?.breached);
    if (filter === "waiting") return all.filter((m) => m.blocker || m.sla?.running === false);
    return all;
  }, [data, filter, me?.id]);

  return (
    <div className="space-y-6">
      <PageTitle
        title="Matters"
        subtitle="A matter is the container for a piece of legal work. Everything attaches to it."
      />

      <div className="flex flex-wrap items-center gap-1.5">
        {FILTERS.map((option) => (
          <Button
            key={option.id}
            size="sm"
            variant={filter === option.id ? "dark" : "default"}
            onClick={() => setFilter(option.id)}
          >
            {option.label}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader title={`${rows.length} matters`} subtitle={`Entity ${entity}`} />
        <div className="table-scroll">
          <div className="min-w-[63.75rem]">
            <Row cols="10.625rem minmax(0,1fr) minmax(0,0.9fr) 4.375rem 8.75rem minmax(0,1fr) 6.875rem" head>
              <div>Matter</div>
              <div>Title</div>
              <div>Counterparty</div>
              <div>Tier</div>
              <div>Status</div>
              <div>Next action</div>
              <div>Service clock</div>
            </Row>

            {loading ? (
              <Spinner />
            ) : error ? (
              <Empty title="Matters are not available to you" detail={error.message} />
            ) : !rows.length ? (
              <Empty title="Nothing matches this filter" />
            ) : (
              rows.map((matter) => (
                <Link
                  key={matter.id}
                  href={`/workspace/matters/${matter.id}`}
                  className="block text-foreground no-underline hover:bg-muted/60"
                >
                  <Row cols="10.625rem minmax(0,1fr) minmax(0,0.9fr) 4.375rem 8.75rem minmax(0,1fr) 6.875rem">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-mono text-2xs text-muted-foreground">{matter.number}</span>
                      {matter.restricted ? (
                        <span title="Restricted matter" aria-label="Restricted matter">
                          &#128274;
                        </span>
                      ) : null}
                    </div>
                    <div className="truncate">{matter.title}</div>
                    <div className="truncate text-muted-foreground">
                      {matter.counterparty?.legal_name ?? "Not linked"}
                    </div>
                    <div>
                      <TierPill tier={matter.risk_tier} />
                    </div>
                    <div>
                      <StatusPill status={matter.status} />
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {matter.blocker ?? matter.next_action ?? "None recorded"}
                    </div>
                    <div>
                      <SlaPill sla={matter.sla} />
                    </div>
                  </Row>
                </Link>
              ))
            )}
          </div>
        </div>
      </Card>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Row-level security scopes this list in the database. A matter in the other entity, or a
        restricted matter you are not named on, is absent rather than hidden, so no title or
        reference to it can appear here.
      </p>
    </div>
  );
}
