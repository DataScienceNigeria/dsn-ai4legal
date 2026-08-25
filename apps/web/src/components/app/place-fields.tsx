"use client";

import * as React from "react";

import { Button, Modal, Notice, Refusal, Spinner } from "@/components/ui";
import { api } from "@/lib/api";

type Session = {
  session_token: string;
  app_id: string;
  server_url: string;
  document: string;
  user: Record<string, unknown>;
};

/*
  Placing the signature fields, without a second sign-in.

  The screen is the signing service's, and should be: the code that places a
  field is the code that later stamps the signature into the PDF, so the
  coordinates are right by construction. Rebuilding it here would mean
  reverse-engineering a coordinate system nobody documented, and a page origin
  off by a little puts a signature in the margin of an executed agreement.

  What was wrong was the seam. On its own origin their client asked for a
  password the person had already given this platform, because a browser keeps
  session state per origin. Their routes are proxied through this origin now,
  so the session can be written before the frame loads and the frame finds
  itself already signed in.

  The session is the platform's single account on the service, which is what
  every document there already belongs to. It grants nothing that issuing the
  request did not, and it is cleared when the dialog closes rather than left
  in the browser of whoever last placed a field.
*/
const KEYS = [
  "accesstoken",
  "parseAppId",
  "baseUrl",
  "UserInformation",
  "_user_role",
  "Extand_Class",
];

function seed(session: Session) {
  const store = globalThis.localStorage;
  store.setItem("accesstoken", session.session_token);
  store.setItem("parseAppId", session.app_id);
  store.setItem("baseUrl", session.server_url);
  store.setItem("UserInformation", JSON.stringify(session.user));
  store.setItem("_user_role", "contracts_Admin");
  store.setItem("Extand_Class", "contracts_Users");
  /*
    The Parse SDK reads its own key and will not take a bare token, so the
    shape it writes on a real sign-in is written here instead.
  */
  store.setItem(
    `Parse/${session.app_id}/currentUser`,
    JSON.stringify({ ...session.user, sessionToken: session.session_token }),
  );
}

function clear(appId: string | null) {
  const store = globalThis.localStorage;
  for (const key of KEYS) store.removeItem(key);
  if (appId) store.removeItem(`Parse/${appId}/currentUser`);
}

export function PlaceFields({
  requestId,
  fallbackUrl,
  onClosed,
}: Readonly<{ requestId: string; fallbackUrl: string; onClosed: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [session, setSession] = React.useState<Session | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function start() {
    setError(null);
    setOpen(true);
    try {
      const opened = await api<Session>(
        `/signature/requests/${requestId}/placement-session`,
        { method: "POST" },
      );
      seed(opened);
      setSession(opened);
    } catch (exception) {
      setError(
        exception instanceof Error
          ? exception.message
          : "The signing service would not open a session.",
      );
    }
  }

  function close() {
    clear(session?.app_id ?? null);
    setSession(null);
    setOpen(false);
    onClosed();
  }

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => void start()}>
        Place the signature fields
      </Button>

      <Modal
        open={open}
        title="Place the signature fields"
        subtitle="Drag a signature box onto each party's line, then send from here. Sending emails every signer a link to the exact document these approvals were given against."
        width="lg"
        onClose={close}
        footer={<Button onClick={close}>Done</Button>}
      >
        {error ? (
          <div className="space-y-3">
            <Refusal title="That could not be opened here" reason={error} />
            <Notice tone="info" title="It can still be done directly">
              <a href={fallbackUrl} target="_blank" rel="noreferrer">
                Open the signing service in a new tab
              </a>
              . You will be asked to sign in there.
            </Notice>
          </div>
        ) : session ? (
          <iframe
            title="Place the signature fields"
            src={`/placeHolderSign/${session.document}`}
            className="h-[min(72vh,44rem)] w-full rounded-md border bg-card"
          />
        ) : (
          <Spinner label="Opening the document" />
        )}
      </Modal>
    </>
  );
}
