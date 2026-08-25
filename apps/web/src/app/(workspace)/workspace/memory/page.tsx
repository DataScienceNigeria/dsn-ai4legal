"use client";

import * as React from "react";

import { Icon } from "@/components/app/icons";
import { AnswerBody as AnswerProse } from "@/components/app/answer";
import { useSession } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  Confirm,
  Input,
  Modal,
  Mono,
  Refusal,
  Spinner,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { Answer, Conversation, ConversationBrief, ConversationTurn } from "@/lib/types";
import { cn, formatDateTime, titleCase } from "@/lib/utils";

const SUGGESTED = [
  "Have we ever accepted uncapped liability, and who approved it?",
  "What notice period do we normally accept on termination for convenience?",
  "What should I know about Sahel Cloud Services before I negotiate?",
  "Summarise the Anambra investigation matter for me.",
];

/*
  A pending turn is held in state rather than written optimistically to the
  thread, because the answer is the part that takes time and a question shown
  without one has to be visibly unanswered rather than silently missing.
*/
type Pending = { question: string } | null;

function when(value: string | null): string {
  if (!value) return "";
  const then = new Date(value).getTime();
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 8) return `${days}d ago`;
  return formatDateTime(value).split(",")[0];
}

function plural(count: number): string {
  return count === 1 ? "" : "s";
}

function deletionDetail(conversation: ConversationBrief): string {
  return (
    `"${conversation.title}" and its ${conversation.message_count} ` +
    `message${plural(conversation.message_count)} go. The AI interaction log stays, so every ` +
    "question that reached a model remains accountable."
  );
}

function AnswerBody({ answer }: Readonly<{ answer: Answer }>) {
  if (answer.refused) {
    return <Refusal title="I cannot answer that" reason={answer.refusal_reason} />;
  }

  return (
    <Card>
      <CardBody className="space-y-3">
        <AnswerProse
          markdown={answer.answer}
          references={answer.sources.map((source) => source.reference)}
        />

        {/*
          What the records did not cover, in the reader's words. It sits under
          the answer as a sentence rather than in a warning panel: it is part
          of the answer, not an incident.
        */}
        {answer.note || answer.suppressed_statements > 0 ? (
          <p className="max-w-reading text-xs leading-relaxed text-muted-foreground">
            {answer.note}
            {answer.suppressed_statements > 0 ? (
              <>
                {answer.note ? " " : ""}
                {answer.suppressed_statements} statement
                {answer.suppressed_statements === 1 ? " was" : "s were"} left out for want of a
                record to support {answer.suppressed_statements === 1 ? "it" : "them"}.
              </>
            ) : null}
          </p>
        ) : null}

        {/*
          The sources, folded away. They are the proof, and proof belongs
          within reach rather than in the middle of the reading: the citations
          in the text already say which record each claim rests on.
        */}
        {answer.sources.length ? (
          <details className="group border-t pt-3">
            <summary className="cursor-pointer list-none text-xs text-muted-foreground hover:text-foreground">
              {answer.sources.length} source{answer.sources.length === 1 ? "" : "s"}
              <span className="ml-1.5 inline-block transition-transform group-open:rotate-90">
                &#9656;
              </span>
            </summary>
            <div className="mt-2.5 space-y-1.5">
              {answer.sources.map((source) => (
                <div key={source.reference} className="flex items-baseline gap-2 text-sm">
                  <Mono>{source.reference}</Mono>
                  <span className="text-muted-foreground">
                    {titleCase(source.kind)}
                    {source.detail ? `, ${source.detail}` : ""}
                  </span>
                </div>
              ))}
              {answer.interaction_id ? (
                <div className="pt-1.5">
                  <Mono>{answer.interaction_id}</Mono>
                </div>
              ) : null}
            </div>
          </details>
        ) : null}
      </CardBody>
    </Card>
  );
}

function Thread({
  turns,
  pending,
}: Readonly<{ turns: ConversationTurn[]; pending: Pending }>) {
  return (
    <div className="space-y-5">
      {turns.map((turn) => (
        <div key={turn.id} className="space-y-3">
          <div className="flex justify-end">
            <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-brand px-3.5 py-2 text-sm text-brand-foreground sm:max-w-[70%]">
              {turn.question}
            </div>
          </div>
          {turn.answer ? <AnswerBody answer={turn.answer} /> : null}
        </div>
      ))}

      {pending ? (
        <div className="space-y-3">
          <div className="flex justify-end">
            <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-brand px-3.5 py-2 text-sm text-brand-foreground sm:max-w-[70%]">
              {pending.question}
            </div>
          </div>
          <Spinner label="Retrieving under your permissions" />
        </div>
      ) : null}
    </div>
  );
}

function ConversationList({
  conversations,
  activeId,
  onOpen,
  onRename,
  onDelete,
}: Readonly<{
  conversations: ConversationBrief[];
  activeId: string | null;
  onOpen: (id: string) => void;
  onRename: (conversation: ConversationBrief) => void;
  onDelete: (conversation: ConversationBrief) => void;
}>) {
  if (conversations.length === 0) {
    return (
      <p className="px-3 py-6 text-sm leading-relaxed text-muted-foreground">
        No conversations yet. Ask something and this thread is kept, so an answer someone relied
        on can be reopened with its citations intact.
      </p>
    );
  }

  return (
    <ul className="space-y-0.5">
      {conversations.map((conversation) => {
        const active = conversation.id === activeId;
        return (
          <li key={conversation.id} className="group relative">
            <button
              type="button"
              onClick={() => onOpen(conversation.id)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "w-full rounded-md py-2 pl-3 pr-16 text-left transition-colors",
                active
                  ? "bg-heading/10 text-heading"
                  : "text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground",
              )}
            >
              <span className="block truncate text-sm font-medium">{conversation.title}</span>
              <span className="mt-0.5 block text-2xs">
                {conversation.message_count} message{plural(conversation.message_count)}
                {conversation.last_message_at ? ` , ${when(conversation.last_message_at)}` : ""}
              </span>
            </button>
            <div className="absolute right-1.5 top-1.5 flex gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
              <button
                type="button"
                onClick={() => onRename(conversation)}
                title="Rename"
                aria-label={`Rename ${conversation.title}`}
                className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
              >
                <Icon name="rename" className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => onDelete(conversation)}
                title="Delete"
                aria-label={`Delete ${conversation.title}`}
                className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
              >
                <Icon name="trash" className="h-4 w-4" />
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/*
  Every call to the API lives here rather than in the component. The component
  is then a description of the screen, and the thing that can actually fail is
  in one place with one error channel.
*/
function useChat(entity: string) {
  const [conversations, setConversations] = React.useState<ConversationBrief[]>([]);
  const [active, setActive] = React.useState<Conversation | null>(null);
  const [pending, setPending] = React.useState<Pending>(null);
  const [error, setError] = React.useState<ApiError | null>(null);
  const [loading, setLoading] = React.useState(true);

  const fail = React.useCallback((exception: unknown) => {
    if (exception instanceof ApiError) setError(exception);
  }, []);

  const loadList = React.useCallback(async () => {
    const rows = await api<ConversationBrief[]>("/ai/conversations");
    setConversations(rows);
    return rows;
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setActive(null);
    loadList()
      .then(async (rows) => {
        if (cancelled || rows.length === 0) return;
        const full = await api<Conversation>(`/ai/conversations/${rows[0].id}`);
        if (!cancelled) setActive(full);
      })
      .catch(fail)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadList, fail, entity]);

  const open = React.useCallback(
    async (id: string) => {
      setError(null);
      try {
        setActive(await api<Conversation>(`/ai/conversations/${id}`));
      } catch (exception) {
        fail(exception);
      }
    },
    [fail],
  );

  const startNew = React.useCallback(() => {
    setActive(null);
    setError(null);
  }, []);

  const send = React.useCallback(
    async (asked: string) => {
      setError(null);
      setPending({ question: asked });
      try {
        if (active) {
          const turn = await api<ConversationTurn>(`/ai/conversations/${active.id}/messages`, {
            method: "POST",
            body: { question: asked },
          });
          setActive((previous) =>
            previous ? { ...previous, turns: [...previous.turns, turn] } : previous,
          );
        } else {
          setActive(
            await api<Conversation>("/ai/conversations", {
              method: "POST",
              body: { question: asked },
            }),
          );
        }
        await loadList();
      } catch (exception) {
        fail(exception);
      } finally {
        setPending(null);
      }
    },
    [active, loadList, fail],
  );

  const rename = React.useCallback(
    async (id: string, title: string) => {
      try {
        await api(`/ai/conversations/${id}`, { method: "PATCH", body: { title } });
        await loadList();
        setActive((previous) => (previous?.id === id ? { ...previous, title } : previous));
      } catch (exception) {
        fail(exception);
      }
    },
    [loadList, fail],
  );

  const remove = React.useCallback(
    async (id: string) => {
      try {
        await api(`/ai/conversations/${id}`, { method: "DELETE" });
        const rows = await loadList();
        setActive((previous) => (previous?.id === id ? null : previous));
        if (rows.length) await open(rows[0].id);
      } catch (exception) {
        fail(exception);
      }
    },
    [loadList, open, fail],
  );

  return {
    conversations,
    active,
    pending,
    error,
    loading,
    open,
    startNew,
    send,
    rename,
    remove,
  };
}

export default function Memory() {
  const { entity } = useSession();
  const chat = useChat(entity);
  const { active, pending, loading } = chat;

  const [question, setQuestion] = React.useState("");
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [renaming, setRenaming] = React.useState<ConversationBrief | null>(null);
  const [renameTo, setRenameTo] = React.useState("");
  const [deleting, setDeleting] = React.useState<ConversationBrief | null>(null);

  const bottom = React.useRef<HTMLDivElement>(null);
  const composer = React.useRef<HTMLTextAreaElement>(null);

  const strapline = active
    ? `${active.message_count} message${plural(active.message_count)}, kept with its citations`
    : `Over the approved library, executed agreements, decision records and playbooks in ${entity}`;

  React.useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [active?.turns.length, pending]);

  function resize() {
    const box = composer.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 200)}px`;
  }

  function ask(text: string) {
    const asked = text.trim();
    if (!asked || pending) return;
    setQuestion("");
    if (composer.current) composer.current.style.height = "auto";
    void chat.send(asked);
  }

  function openThread(id: string) {
    setHistoryOpen(false);
    void chat.open(id);
  }

  function newThread() {
    setHistoryOpen(false);
    chat.startNew();
    composer.current?.focus();
  }

  const history = (
    <div className="flex h-full flex-col">
      <div className="border-b p-3">
        <Button variant="primary" className="w-full" onClick={newThread}>
          <Icon name="plus" className="h-4 w-4" />
          New conversation
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        <ConversationList
          conversations={chat.conversations}
          activeId={active?.id ?? null}
          onOpen={openThread}
          onRename={(conversation) => {
            setRenameTo(conversation.title);
            setRenaming(conversation);
          }}
          onDelete={(conversation) => setDeleting(conversation)}
        />
      </div>
    </div>
  );

  return (
    <div className="flex h-[calc(100vh-8.5rem)] min-h-[34rem] gap-4">
      <aside className="hidden w-[16rem] shrink-0 overflow-hidden rounded-lg border bg-card lg:block xl:w-[18rem]">
        {history}
      </aside>

      {historyOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close the conversation list"
            className="absolute inset-0 bg-foreground/40"
            onClick={() => setHistoryOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-[17rem] max-w-[85vw] border-r bg-card shadow-xl">
            {history}
          </div>
        </div>
      ) : null}

      <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border bg-card">
        <header className="flex shrink-0 items-center gap-3 border-b px-4 py-3">
          <Button
            variant="ghost"
            size="sm"
            className="lg:hidden"
            aria-label="Open the conversation list"
            onClick={() => setHistoryOpen(true)}
          >
            <Icon name="chat" className="h-4 w-4" />
          </Button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-base font-semibold text-heading">
              {active ? active.title : "Ask memory"}
            </h1>
            <p className="truncate text-xs text-muted-foreground">{strapline}</p>
          </div>
          {active ? (
            <Button size="sm" onClick={newThread}>
              <Icon name="plus" className="h-4 w-4" />
              <span className="hidden sm:inline">New</span>
            </Button>
          ) : null}
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-5">
          {loading ? <Spinner label="Opening your conversations" /> : null}
          {!loading && active ? <Thread turns={active.turns} pending={pending} /> : null}
          {!loading && !active ? (
            <div className="mx-auto max-w-reading space-y-4 py-6">
              <div>
                <h2 className="text-xl font-semibold text-heading">Ask memory</h2>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  This memory builds itself from normal work. Decision entries, accepted redlines,
                  approved fallback usage and executed agreements are indexed on the events that
                  create them, so there is no separate knowledge-entry task. Any statement without
                  a citation is suppressed rather than shown.
                </p>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {SUGGESTED.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => ask(prompt)}
                    className="rounded-md border px-3 py-2.5 text-left text-sm transition-colors hover:bg-foreground/[0.06]"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
              {pending ? <Thread turns={[]} pending={pending} /> : null}
            </div>
          ) : null}
          {chat.error ? (
            <div className="mt-4">
              <Refusal title="That did not go through" reason={chat.error.message} />
            </div>
          ) : null}
          <div ref={bottom} />
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            ask(question);
          }}
          className="shrink-0 border-t p-3 sm:p-4"
        >
          <div className="flex items-end gap-2 rounded-lg border bg-background p-2 focus-within:ring-2 focus-within:ring-ring">
            <textarea
              ref={composer}
              rows={1}
              value={question}
              onChange={(event) => {
                setQuestion(event.target.value);
                resize();
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  ask(question);
                }
              }}
              placeholder={`Ask about ${entity} positions, agreements or decisions`}
              className="max-h-[12.5rem] min-h-[2.25rem] flex-1 resize-none bg-transparent px-1.5 py-1.5 text-sm outline-none placeholder:text-muted-foreground"
            />
            <Button
              type="submit"
              variant="primary"
              disabled={!!pending || !question.trim()}
              aria-label="Send"
            >
              <Icon name="send" className="h-4 w-4" />
              <span className="hidden sm:inline">Ask</span>
            </Button>
          </div>
          <p className="mt-2 text-2xs leading-relaxed text-muted-foreground">
            Enter sends, shift and enter starts a line. Retrieval filters by entity, role and
            matter access before ranking rather than after, so a record you cannot open never
            enters the candidate set. The thread is yours alone: nobody else can open it.
          </p>
        </form>
      </section>

      <Modal
        open={renaming !== null}
        title="Name this conversation"
        subtitle="The name is how you will find this thread again."
        width="sm"
        onClose={() => setRenaming(null)}
        footer={
          <>
            <Button onClick={() => setRenaming(null)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!renameTo.trim()}
              onClick={() => {
                const target = renaming;
                setRenaming(null);
                if (target) void chat.rename(target.id, renameTo.trim());
              }}
            >
              Rename
            </Button>
          </>
        }
      >
        <Input
          value={renameTo}
          maxLength={200}
          onChange={(event) => setRenameTo(event.target.value)}
          aria-label="Conversation name"
        />
      </Modal>

      <Confirm
        open={deleting !== null}
        destructive
        title="Delete this conversation"
        confirmLabel="Delete"
        detail={deleting ? deletionDetail(deleting) : undefined}
        onCancel={() => setDeleting(null)}
        onConfirm={() => {
          const target = deleting;
          setDeleting(null);
          if (target) void chat.remove(target.id);
        }}
      />
    </div>
  );
}
