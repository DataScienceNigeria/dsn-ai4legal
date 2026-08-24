"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { Icon } from "@/components/app/icons";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { NotificationItem, NotificationPage } from "@/lib/types";
import { cn, relativeHours } from "@/lib/utils";

const KIND_LABEL: Record<string, string> = {
  matter_assigned: "Assigned",
  matter_reassigned: "Reassigned",
  approval_waiting: "Approval",
  approval_decided: "Approval",
  findings_raised: "Review",
  request_returned: "Request",
};

function age(iso: string): string {
  const hours = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  return hours < 1 ? "just now" : `${relativeHours(hours)} ago`;
}

/*
  The bell. Work routed to a person was announced only through the outbox,
  which carries mail to an external connector the platform may not be cleared
  or configured to use, so nothing reached them inside the product.

  Scoped to the working entity like everything else. Switching organisation
  changes what is in the bell, because the work behind it belongs to one
  organisation and clearing it in the other would be a different queue.
*/
export function Notifications({ entity }: Readonly<{ entity: string }>) {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const box = React.useRef<HTMLDivElement>(null);
  const page = useApi<NotificationPage>("/workspace/notifications", [entity]);

  React.useEffect(() => setOpen(false), [entity]);

  React.useEffect(() => {
    if (!open) return;
    function away(event: MouseEvent) {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const unread = page.data?.unread ?? 0;
  const items = page.data?.notifications ?? [];

  async function openItem(item: NotificationItem) {
    setOpen(false);
    if (!item.read_at) {
      try {
        await api(`/workspace/notifications/${item.id}/read`, { method: "POST" });
        page.reload();
      } catch {
        // Marking as read is a convenience. A failure here must not stop the
        // person reaching the record the notification is about.
      }
    }
    if (item.href) router.push(item.href);
  }

  async function clearAll() {
    setBusy(true);
    try {
      await api("/workspace/notifications/read-all", { method: "POST" });
      page.reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
        className="relative flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
      >
        <Icon name="bell" className="h-[1.15rem] w-[1.15rem]" />
        {unread > 0 ? (
          <span className="absolute -right-1 -top-1 flex h-[1.1rem] min-w-[1.1rem] items-center justify-center rounded-full bg-destructive px-1 text-2xs font-semibold tabular-nums text-destructive-foreground ring-2 ring-card">
            {unread > 9 ? "9+" : unread}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 z-40 mt-1.5 w-[min(24rem,calc(100vw-2rem))] overflow-hidden rounded-lg border bg-popover shadow-lg">
          <div className="flex items-center justify-between gap-3 border-b px-3.5 py-2.5">
            <span className="text-sm font-medium">
              {unread ? `${unread} unread` : "Nothing unread"}
            </span>
            {unread > 0 ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void clearAll()}
                className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-50"
              >
                Mark all read
              </button>
            ) : null}
          </div>

          {items.length === 0 ? (
            <p className="px-3.5 py-6 text-sm leading-relaxed text-muted-foreground">
              Nothing yet in {entity}. Work assigned to you, an approval reaching you and
              findings raised on your matters arrive here.
            </p>
          ) : (
            <ul className="max-h-[26rem] overflow-y-auto py-1">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => void openItem(item)}
                    className={cn(
                      "flex w-full flex-col gap-1 px-3.5 py-2.5 text-left transition-colors hover:bg-muted",
                      !item.read_at && "bg-brand/[0.06]",
                    )}
                  >
                    <span className="flex items-center gap-2">
                      {!item.read_at ? (
                        <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                      ) : (
                        <Icon
                          name="check"
                          className="h-3 w-3 shrink-0 text-muted-foreground/60"
                        />
                      )}
                      <span className="text-2xs uppercase tracking-wide text-muted-foreground">
                        {KIND_LABEL[item.kind] ?? item.kind.replace(/_/g, " ")}
                      </span>
                      <span className="ml-auto shrink-0 text-2xs text-muted-foreground">
                        {age(item.created_at)}
                      </span>
                    </span>
                    <span className="text-sm font-medium leading-snug">{item.title}</span>
                    {item.body ? (
                      <span className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                        {item.body}
                      </span>
                    ) : null}
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
