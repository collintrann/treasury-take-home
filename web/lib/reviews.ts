import { useSyncExternalStore } from "react";
import { checkQueued, type CheckResult } from "./api";

// Check results and decisions for queued applications. They live in memory and
// in sessionStorage only, so nothing outlives the browser tab.

export type Decision = "approve" | "needs_correction" | "reject";

export type CheckState =
  | { kind: "idle" }
  | { kind: "checking"; startedAt: number }
  | { kind: "done"; result: CheckResult }
  | { kind: "error"; message: string };

export interface Review {
  check: CheckState;
  decision: Decision | null;
}

type Reviews = Readonly<Record<string, Review>>;
type Saved = Record<string, { result: CheckResult | null; decision: Decision | null }>;

const STORAGE_KEY = "label-check:reviews";
const NO_REVIEWS: Reviews = {};
const UNREVIEWED: Review = { check: { kind: "idle" }, decision: null };

let reviews: Reviews | null = null;
const listeners = new Set<() => void>();

function load(): Reviews {
  try {
    const saved: Saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "{}");
    return Object.fromEntries(
      Object.entries(saved).map(([id, { result, decision }]) => [
        id,
        { check: result ? { kind: "done", result } : { kind: "idle" }, decision },
      ]),
    );
  } catch {
    return NO_REVIEWS;
  }
}

function snapshot(): Reviews {
  return (reviews ??= load());
}

function save(all: Reviews) {
  const saved: Saved = Object.fromEntries(
    Object.entries(all).map(([id, { check, decision }]) => [
      id,
      { result: check.kind === "done" ? check.result : null, decision },
    ]),
  );
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
  } catch {
    // Storage full or blocked: results still last until the page reloads.
  }
}

function update(id: string, change: Partial<Review>) {
  const all = snapshot();
  reviews = { ...all, [id]: { ...(all[id] ?? UNREVIEWED), ...change } };
  save(reviews);
  listeners.forEach((notify) => notify());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useReviews(): Reviews {
  return useSyncExternalStore(subscribe, snapshot, () => NO_REVIEWS);
}

export function useReview(id: string): Review {
  return useReviews()[id] ?? UNREVIEWED;
}

export async function runCheck(id: string) {
  if (snapshot()[id]?.check.kind === "checking") return;
  update(id, { check: { kind: "checking", startedAt: Date.now() } });
  try {
    update(id, { check: { kind: "done", result: await checkQueued(id) } });
  } catch (error) {
    update(id, { check: { kind: "error", message: (error as Error).message } });
  }
}

// Reads the store itself rather than a rendered value, which is still empty
// during hydration and would start a second check.
export function checkIfNew(id: string) {
  if ((snapshot()[id] ?? UNREVIEWED).check.kind === "idle") void runCheck(id);
}

export function decide(id: string, decision: Decision | null) {
  update(id, { decision });
}
