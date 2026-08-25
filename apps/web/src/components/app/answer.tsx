"use client";

import * as React from "react";

/*
  An answer, rendered as the writing it is.

  Answers used to arrive as a list of paragraphs, each carrying its citations
  as pills on the end. The shape produced the prose: a stack of disconnected
  sentences, every one of them terminating in a reference, reading like a
  compliance report rather than like a colleague answering a question. The
  model now writes Markdown and cites inline, and this renders it.

  A deliberately small Markdown subset, and written here rather than pulled in:
  the model is told what to write, so what arrives is headings, bold, lists and
  paragraphs. Everything outside that subset renders as the text it is, which
  is the correct failure: an answer about a contract must never turn into an
  interpretation of a contract's punctuation.

  Citations are the one addition. `[EAI-CON-2026-0040]` becomes a quiet marker
  in the line where the claim is made, because a citation is a footnote and not
  a headline. Anything in square brackets that is not a reference we were given
  stays as written, so a model that invents one is visible rather than dressed
  up as a source.
*/

/*
  A citation, including a clause of an agreement: "EAI-CON-2026-0040 cl. 6.2".
  Spaces belong in the pattern, because that is how a claim points at the
  paragraph it came from, and a pattern that stopped at the space rendered
  every clause citation as plain text.
*/
const CITATION = /\[([A-Za-z][A-Za-z0-9\-./ ]{2,63})\]/g;
const BOLD = /\*\*([^*]+)\*\*/g;

function Citation({ reference }: Readonly<{ reference: string }>) {
  return (
    <span className="mx-0.5 whitespace-nowrap rounded border border-info/30 bg-info/10 px-1 align-baseline font-mono text-2xs text-info-foreground dark:text-info">
      {reference}
    </span>
  );
}

/*
  One line of text: bold spans, and citations that the answer's own sources
  vouch for. `known` is the set of references actually retrieved, so a citation
  the model made up is left as plain text rather than rendered as though the
  platform stood behind it.
*/
function Inline({ text, known }: Readonly<{ text: string; known: Set<string> }>) {
  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  let key = 0;

  for (const match of text.matchAll(CITATION)) {
    const at = match.index ?? 0;
    if (at > cursor) nodes.push(<Bold key={key++} text={text.slice(cursor, at)} />);
    if (known.has(match[1])) {
      nodes.push(<Citation key={key++} reference={match[1]} />);
    } else {
      nodes.push(<Bold key={key++} text={match[0]} />);
    }
    cursor = at + match[0].length;
  }
  if (cursor < text.length) nodes.push(<Bold key={key++} text={text.slice(cursor)} />);
  return <>{nodes}</>;
}

function Bold({ text }: Readonly<{ text: string }>) {
  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  let key = 0;
  for (const match of text.matchAll(BOLD)) {
    const at = match.index ?? 0;
    if (at > cursor) nodes.push(text.slice(cursor, at));
    nodes.push(
      <strong key={key++} className="font-semibold text-foreground">
        {match[1]}
      </strong>,
    );
    cursor = at + match[0].length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return <>{nodes}</>;
}

type Block =
  | { kind: "heading"; level: 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] };

function parse(markdown: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  function closeParagraph() {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  }
  function closeList() {
    if (list) {
      blocks.push({ kind: "list", ...list });
      list = null;
    }
  }

  for (const raw of markdown.split("\n")) {
    const line = raw.trim();

    if (!line) {
      closeParagraph();
      closeList();
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      closeParagraph();
      closeList();
      blocks.push({
        kind: "heading",
        level: heading[1].length <= 2 ? 2 : 3,
        text: heading[2],
      });
      continue;
    }

    const bullet = /^[-*+]\s+(.*)$/.exec(line);
    const numbered = /^\d+[.)]\s+(.*)$/.exec(line);
    if (bullet || numbered) {
      closeParagraph();
      const ordered = Boolean(numbered);
      if (!list || list.ordered !== ordered) {
        closeList();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? numbered)![1]);
      continue;
    }

    closeList();
    paragraph.push(line);
  }

  closeParagraph();
  closeList();
  return blocks;
}

export function AnswerBody({
  markdown,
  references,
}: Readonly<{ markdown: string; references: string[] }>) {
  const known = React.useMemo(() => new Set(references), [references]);
  const blocks = React.useMemo(() => parse(markdown), [markdown]);

  return (
    <div className="max-w-reading space-y-3 text-sm leading-relaxed">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          return block.level === 2 ? (
            <h3 key={index} className="pt-1 text-base font-semibold text-foreground">
              <Inline text={block.text} known={known} />
            </h3>
          ) : (
            <h4 key={index} className="pt-1 text-sm font-semibold text-foreground">
              <Inline text={block.text} known={known} />
            </h4>
          );
        }
        if (block.kind === "list") {
          const Tag = block.ordered ? "ol" : "ul";
          return (
            <Tag
              key={index}
              className={
                block.ordered
                  ? "ml-5 list-decimal space-y-1.5 marker:text-muted-foreground"
                  : "ml-5 list-disc space-y-1.5 marker:text-muted-foreground"
              }
            >
              {block.items.map((item, position) => (
                <li key={position}>
                  <Inline text={item} known={known} />
                </li>
              ))}
            </Tag>
          );
        }
        return (
          <p key={index}>
            <Inline text={block.text} known={known} />
          </p>
        );
      })}
    </div>
  );
}
