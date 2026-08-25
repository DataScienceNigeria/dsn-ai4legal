"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { ApiError, api, getEntity, setEntity as persistEntity } from "@/lib/api";
import type { Me } from "@/lib/types";

type Status = "loading" | "ready" | "unauthenticated" | "unreachable";

type SessionValue = {
  me: Me | null;
  status: Status;
  loading: boolean;
  error: string | null;
  entity: string;
  setEntity: (entity: string) => void;
  refresh: () => Promise<void>;
};

const SessionContext = React.createContext<SessionValue>({
  me: null,
  status: "loading",
  loading: true,
  error: null,
  entity: "EAI",
  setEntity: () => undefined,
  refresh: async () => undefined,
});

export function useSession() {
  return React.useContext(SessionContext);
}

/*
  Effective permission is role, entity and matter access together. This covers
  the role half, so a screen can hide an action the API would refuse instead of
  offering it and explaining afterwards.
*/
export function useRoles() {
  const { me } = React.useContext(SessionContext);
  const roles = React.useMemo(() => me?.roles ?? [], [me]);

  return React.useMemo(
    () => ({
      roles,
      has: (...wanted: string[]) => wanted.some((role) => roles.includes(role)),
      isHeadOfLegal: roles.includes("head_of_legal"),
      isLegal: roles.includes("counsel"),
      isAdmin: roles.includes("admin"),
      isAuditor: roles.includes("auditor"),
      readOnly: roles.length > 0 && roles.every((role) => role === "auditor" || role === "management"),
    }),
    [roles],
  );
}

export function SessionProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter();
  const [me, setMe] = React.useState<Me | null>(null);
  const [status, setStatus] = React.useState<Status>("loading");
  const [error, setError] = React.useState<string | null>(null);
  const [entity, setEntityState] = React.useState("EAI");

  const load = React.useCallback(async () => {
    setStatus("loading");
    try {
      const result = await api<Me>("/auth/me");
      setMe(result);
      const stored = getEntity();
      setEntityState(result.entities.includes(stored) ? stored : (result.entities[0] ?? "EAI"));
      setError(null);
      setStatus("ready");
    } catch (exception) {
      setMe(null);
      // A rejected token means sign in again. Anything else means the API is
      // not answering, and saying so beats spinning for ever.
      if (exception instanceof ApiError && exception.status === 401) {
        setStatus("unauthenticated");
      } else {
        setError(
          exception instanceof ApiError
            ? exception.message
            : "The API did not respond. Check that it is running and reachable.",
        );
        setStatus("unreachable");
      }
    }
  }, []);

  // Runs once. Depending on the router here re-ran it on every render.
  React.useEffect(() => {
    void load();
  }, [load]);

  React.useEffect(() => {
    if (status === "unauthenticated") router.replace("/sign-in");
  }, [status, router]);

  const setEntity = React.useCallback((next: string) => {
    persistEntity(next);
    setEntityState(next);
  }, []);

  /*
    The organisation tint is a token swap on the root element, so it belongs
    with the state that decides it rather than with any one screen. The
    pre-paint script in the layout sets the same attribute from storage; this
    keeps it true after a switch and after the API corrects an entity the
    account does not hold.
  */
  React.useEffect(() => {
    document.documentElement.dataset.entity = entity;
  }, [entity]);

  const value = React.useMemo(
    () => ({
      me,
      status,
      loading: status === "loading",
      error,
      entity,
      setEntity,
      refresh: load,
    }),
    [me, status, error, entity, setEntity, load],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
