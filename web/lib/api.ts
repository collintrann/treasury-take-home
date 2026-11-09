import type { FieldKey } from "./fields";

export type ProductType = "distilled_spirits" | "wine" | "malt_beverage";
export type Application = Record<FieldKey, string>;

export interface QueueItem {
  id: string;
  submitted_at: string;
  applicant: string;
  product_type: ProductType;
  brand_name: string;
  // Same-origin paths such as /samples/queue/COLA-26-0001.png, front panel first.
  images: string[];
  // The record in TTB's Public COLA Registry. Present only for real applications.
  registry_url: string | null;
}

export interface QueuedApplication extends Omit<QueueItem, "brand_name"> {
  application: Application;
}

export type Overall = "pass" | "fail" | "needs_review";
export type FindingStatus = Overall | "not_evaluated";
export type FindingGroup = "application" | "warning";

export interface DiffPart {
  op: "equal" | "missing" | "extra";
  text: string;
}

export interface Finding {
  key: string;
  group: FindingGroup;
  label: string;
  status: FindingStatus;
  expected: string | null;
  observed: string | null;
  explanation: string;
  diff: DiffPart[] | null;
}

export interface CheckResult {
  overall: Overall;
  image_assessable: boolean;
  image_note: string;
  findings: Finding[];
  elapsed_ms: number;
}

export const UNREACHABLE = "We couldn't reach the checker. Please try again.";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error(UNREACHABLE);
  }
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Not JSON, e.g. a hosting error page.
  }
  return `Something went wrong (error ${res.status}). Please try again.`;
}

const queuePath = (id: string) => `/api/queue/${encodeURIComponent(id)}`;

export const getQueue = () => call<QueueItem[]>("/api/queue");

export const getApplication = (id: string) => call<QueuedApplication>(queuePath(id));

export const checkQueued = (id: string) => call<CheckResult>(`${queuePath(id)}/check`, { method: "POST" });
