"use client";

import * as React from "react";

import { ApiError, api } from "@/lib/api";

type State<T> = { data: T | null; error: ApiError | null; loading: boolean };

export function useApi<T>(path: string | null, deps: unknown[] = []): State<T> & {
  reload: () => void;
} {
  const [state, setState] = React.useState<State<T>>({
    data: null,
    error: null,
    loading: true,
  });
  const [nonce, setNonce] = React.useState(0);

  React.useEffect(() => {
    if (!path) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let cancelled = false;
    setState((previous) => ({ ...previous, loading: true }));

    api<T>(path)
      .then((data) => {
        if (!cancelled) setState({ data, error: null, loading: false });
      })
      .catch((error) => {
        if (!cancelled) {
          setState({
            data: null,
            error:
              error instanceof ApiError
                ? error
                : new ApiError(0, { code: "network", message: "The API could not be reached." }),
            loading: false,
          });
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, nonce, ...deps]);

  return { ...state, reload: () => setNonce((value) => value + 1) };
}

/*
  A refusal for want of a fresh authentication is not a failure, it is a
  question. Every privileged action goes through this hook, so it is answered
  once here: the arguments are held, the caller raises the step-up dialog, and
  `retry` runs the same action again once the caller has re-authenticated.
*/
export function useAction<TArgs extends unknown[], TResult>(
  action: (...args: TArgs) => Promise<TResult>,
) {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<ApiError | null>(null);
  const [stepUpFor, setStepUpFor] = React.useState<string | null>(null);
  const pending = React.useRef<TArgs | null>(null);

  const run = React.useCallback(
    async (...args: TArgs): Promise<TResult | null> => {
      setBusy(true);
      setError(null);
      try {
        return await action(...args);
      } catch (exception) {
        if (exception instanceof ApiError && exception.problem.code === "step_up_required") {
          pending.current = args;
          setStepUpFor(exception.message);
          return null;
        }
        setError(
          exception instanceof ApiError
            ? exception
            : new ApiError(0, { code: "network", message: "The action could not be completed." }),
        );
        return null;
      } finally {
        setBusy(false);
      }
    },
    [action],
  );

  const retry = React.useCallback(async () => {
    const args = pending.current;
    pending.current = null;
    setStepUpFor(null);
    if (args) await run(...args);
  }, [run]);

  return {
    run,
    busy,
    error,
    clearError: () => setError(null),
    /** The refusal message, while a fresh authentication is outstanding. */
    stepUpFor,
    dismissStepUp: () => {
      pending.current = null;
      setStepUpFor(null);
    },
    retry,
  };
}
