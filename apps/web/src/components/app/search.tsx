"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { api } from "@/lib/api";
import type { SearchHit, SearchResults } from "@/lib/types";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<string, string> = {
  matter: "Matter",
  request: "Request",
  contract: "Contract",
  template: "Template",
  counterparty: "Counterparty",
  obligation: "Obligation",
};

/*
  Finding a record you can already name. Deliberately not Ask memory, which
  answers a question from the records and cites what it used. This resolves an
  identifier to the screen that holds it and claims nothing about it, so the
  two are not confusable: one is a lookup, the other is an answer.

  Scoping is the API's, not the field's. A restricted matter the caller is not
  named on is absent from the results rather than shown and refused on open.
*/
export function Search({ entity }: Readonly<{ entity: string }>) {
  const router = useRouter();
  const [term, setTerm] = React.useState("");
  const [hits, setHits] = React.useState<SearchHit[]>([]);
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [cursor, setCursor] = React.useState(0);
  const box = React.useRef<HTMLDivElement>(null);
  const field = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    setTerm("");
    setHits([]);
    setOpen(false);
  }, [entity]);

  /*
    Debounced, because a keystroke is not a question. Every response is
    checked against the term that is current when it lands, so a slow answer
    to "om" cannot overwrite a fast answer to "omni".
  */
  React.useEffect(() => {
    const query = term.trim();
    if (query.length < 2) {
      setHits([]);
      setBusy(false);
      return;
    }
    let cancelled = false;
    setBusy(true);
    const timer = globalThis.setTimeout(() => {
      api<SearchResults>(`/workspace/search?q=${encodeURIComponent(query)}`)
        .then((result) => {
          if (cancelled) return;
          setHits(result.hits);
          setCursor(0);
          setOpen(true);
        })
        .catch(() => {
          if (!cancelled) setHits([]);
        })
        .finally(() => {
          if (!cancelled) setBusy(false);
        });
    }, 220);
    return () => {
      cancelled = true;
      globalThis.clearTimeout(timer);
    };
  }, [term]);

  React.useEffect(() => {
    function away(event: MouseEvent) {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);

  React.useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        field.current?.focus();
      }
    }
    globalThis.addEventListener("keydown", shortcut);
    return () => globalThis.removeEventListener("keydown", shortcut);
  }, []);

  function go(hit: SearchHit) {
    setOpen(false);
    setTerm("");
    setHits([]);
    router.push(hit.href);
  }

  function onKey(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      field.current?.blur();
      return;
    }
    if (!hits.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((at) => (at + 1) % hits.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((at) => (at - 1 + hits.length) % hits.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(hits[cursor]);
    }
  }

  const searching = term.trim().length >= 2;

  return (
    <div ref={box} className="relative w-full max-w-md">
      <label htmlFor="workspace-search" className="sr-only">
        Find a matter, contract, template or counterparty
      </label>
      <div className="relative">
        <span
          aria-hidden
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground"
        >
          &#9906;
        </span>
        <input
          id="workspace-search"
          ref={field}
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          onFocus={() => hits.length && setOpen(true)}
          onKeyDown={onKey}
          autoComplete="off"
          placeholder="Find a matter, contract, template, counterparty"
          className="h-9 w-full rounded-md border border-input bg-muted/60 pl-9 pr-14 text-sm placeholder:text-muted-foreground focus-visible:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
        />
        <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border bg-card px-1.5 py-0.5 font-mono text-2xs text-muted-foreground sm:block">
          &#8984;K
        </kbd>
      </div>

      {open && searching ? (
        <div className="absolute left-0 right-0 z-40 mt-1.5 overflow-hidden rounded-lg border bg-popover shadow-lg">
          {hits.length === 0 ? (
            <div className="px-3.5 py-4 text-sm text-muted-foreground">
              {busy ? "Looking" : `Nothing in ${entity} matches that.`}
            </div>
          ) : (
            <ul className="max-h-[22rem] overflow-y-auto py-1">
              {hits.map((hit, index) => (
                <li key={`${hit.kind}-${hit.reference}`}>
                  <button
                    type="button"
                    onMouseEnter={() => setCursor(index)}
                    onClick={() => go(hit)}
                    className={cn(
                      "flex w-full items-center gap-3 px-3.5 py-2 text-left transition-colors",
                      index === cursor ? "bg-brand/[0.08]" : "hover:bg-muted",
                    )}
                  >
                    <span className="w-24 shrink-0 text-2xs uppercase tracking-wide text-muted-foreground">
                      {KIND_LABEL[hit.kind] ?? hit.kind}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm">{hit.label}</span>
                    <span className="shrink-0 font-mono text-2xs text-muted-foreground">
                      {hit.reference}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
