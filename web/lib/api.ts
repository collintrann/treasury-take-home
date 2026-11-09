import type { Application } from "./fields";
import { shrinkForUpload } from "./image";

// Response shapes from the checker service (app/models.py and app/main.py).

export type Verdict = "pass" | "review" | "fail";
export type FieldStatus = Verdict | "missing" | "skipped";

export interface DiffPart {
  op: "equal" | "missing" | "extra";
  text: string;
}

export interface FieldResult {
  field: string;
  label: string;
  expected: string | null;
  found: string | null;
  status: FieldStatus;
  note: string;
  diff: DiffPart[] | null;
  agreement: "agreed" | "disputed" | "single" | null;
}

export interface VerificationResult {
  overall: Verdict;
  fields: FieldResult[];
  readers: string[];
  extraction_note: string;
  elapsed_ms: number;
  filename: string | null;
}

export interface ManifestRow {
  filename: string;
  application: Application;
}

export interface ParsedManifest {
  rows: ManifestRow[];
  errors: string[];
}

export interface Example extends ManifestRow {
  what_this_tests: string;
}

export const UNREACHABLE = "We couldn't reach the checker. Please try again.";

async function call(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error(UNREACHABLE);
  }
  if (!res.ok) throw new Error(await errorMessage(res));
  return res;
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

export async function verifyLabel(image: File, application: Application): Promise<VerificationResult> {
  const upload = await shrinkForUpload(image);
  const form = new FormData();
  form.append("image", upload, upload.name);
  for (const [key, value] of Object.entries(application)) form.append(key, value);
  return (await call("/api/verify", { method: "POST", body: form })).json();
}

export async function parseManifest(csv: File): Promise<ParsedManifest> {
  const form = new FormData();
  form.append("manifest", csv, csv.name);
  return (await call("/api/parse-manifest", { method: "POST", body: form })).json();
}

export async function getExamples(): Promise<Example[]> {
  return (await call("/api/examples")).json();
}

export async function fetchSample(filename: string): Promise<File> {
  const blob = await (await call(`/samples/${encodeURIComponent(filename)}`)).blob();
  return new File([blob], filename, { type: blob.type });
}
