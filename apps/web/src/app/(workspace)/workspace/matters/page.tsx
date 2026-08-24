"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";

import { useSession } from "@/components/app/session";
import { SlaPill, StatusPill, TierPill } from "@/components/app/status";
import { Card, CardHeader, Chips, Empty, Notice, PageTitle, Row, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { Matter } from "@/lib/types";
import { titleCase } from "@/lib/utils";

const FILTERS = [
  { id: "all", label: "All open" },
  { id: "mine", label: "Mine" },
  { id: "breach", label: "Past target" },
  { id: "waiting", label: "Waiting on someone" },
];

/*
  The filter is in the query string, so a figure on the delivery dashboard can
  link straight to the matters behind it and the reader can send that link on.
*/
const FILTER_IDS = new Set(FILTERS.map((option) => option.id));

function narrowedTo(ownerName: string | null, tier: string | null): string {
  const parts: string[] = [];
  if (ownerName) parts.push(`${ownerName}'s matters`);
  if (tier) parts.push(titleCase(tier));
  return `Showing only ${parts.join(", ") || "part of the list"}`;
}

export default function Matters() {
  const { entity, me } = useSession();
  const params = useSearchParams();
  const requested = params.get("filter") ?? "all";
  const owner = params.get("owner");
  const ownerName = params.get("owner_name");
  const tier = params.get("tier");
  const [filter, setFilter] = React.useState(FILTER_IDS.has(requested) ? requested : "all");
  const { data, loading, error } = useApi<Matter[]>("/matters", [entity]);

  const rows = React.useMemo(() => {
    let all = data ?? [];
    if (owner) all = all.filter((m) => m.responsible_lawyer_id === owner);
    if (tier) all = all.filter((m) => m.risk_tier === tier);
    if (filter === "mine") return all.filter((m) => m.responsible_lawyer_id === me?.id);
    if (filter === "breach") return all.filter((m) => m.sla?.breached);
    if (filter === "waiting") return all.filter((m) => m.blocker || m.sla?.running === false);
    return all;
  }, [data, filter, owner, tier, me?.id]);

  /*
    Each chip carries how many it would leave. A filter that turns out to be
    empty is worth knowing before pressing it, not after.
  */
  const chips = React.useMemo(() => {
    let scoped = data ?? [];
    if (owner) scoped = scoped.filter((m) => m.responsible_lawyer_id === owner);
    if (tier) scoped = scoped.filter((m) => m.risk_tier === tier);
    const sizes: Record<string, number> = {
      all: scoped.length,
      mine: scoped.filter((m) => m.responsible_lawyer_id === me?.id).length,
      breach: scoped.filter((m) => m.sla?.breached).length,
      waiting: scoped.filter((m) => m.blocker || m.sla?.running === false).length,
    };
    return FILTERS.map((option) => ({ ...option, count: sizes[option.id] ?? 0 }));
  }, [data, owner, tier, me?.id]);

  return (
    <div className="space-y-6">
      <PageTitle
        title="Matters"
        subtitle="A matter is the container for a piece of legal work. Everything attaches to it."
      />

      {owner || tier ? (
        <Notice tone="info" title={narrowedTo(ownerName, tier)}>
          You arrived from the delivery dashboard.{" "}
          <Link href="/workspace/matters">Show everything</Link>.
        </Notice>
      ) : null}

      <Chips options={chips} active={filter} onChange={setFilter} label="Narrow the matters" />

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
