import { useCallback, useEffect, useState } from "react";

export type Load<T> = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: T };

// Runs `load` on mount and on retry. `load` must be stable (module-level or memoized).
export function useLoad<T>(load: () => Promise<T>): { state: Load<T>; retry: () => void } {
  const [state, setState] = useState<Load<T>>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    load().then(
      (data) => current && setState({ kind: "ready", data }),
      (error: Error) => current && setState({ kind: "error", message: error.message }),
    );
    return () => {
      current = false;
    };
  }, [load, attempt]);

  const retry = useCallback(() => {
    setState({ kind: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  return { state, retry };
}
