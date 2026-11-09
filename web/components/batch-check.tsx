"use client";

import { useState } from "react";
import { LoaderCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ResultView } from "@/components/result-view";
import { StatusBadge, VERDICT } from "@/components/status";
import { Step } from "@/components/step";
import { APPLICATION_FIELDS, IDENTIFYING_FIELD } from "@/lib/fields";
import {
  fetchSample,
  parseManifest,
  verifyLabel,
  type ManifestRow,
  type Verdict,
  type VerificationResult,
} from "@/lib/api";

// The checker also limits this; 4 keeps the browser responsive.
const CONCURRENCY = 4;

type Outcome = { kind: "result"; result: VerificationResult } | { kind: "error"; message: string };

interface Run {
  rows: ManifestRow[];
  outcomes: (Outcome | null)[];
  seconds?: number;
}

type Filter = "all" | Verdict;
const FILTERS: [Filter, string][] = [
  ["all", "All"],
  ["fail", "Problems"],
  ["review", "Needs review"],
  ["pass", "Passed"],
];

function verdictOf(outcome: Outcome): Verdict {
  return outcome.kind === "error" ? "fail" : outcome.result.overall;
}

function issues(outcome: Outcome): string {
  if (outcome.kind === "error") return outcome.message;
  const flagged = outcome.result.fields.filter((f) => f.status !== "pass" && f.status !== "skipped");
  return flagged.map((f) => `${f.label}: ${f.note}`).join(" · ") || "None";
}

async function checkOne(row: ManifestRow, image: File | undefined): Promise<Outcome> {
  if (!image) return { kind: "error", message: "No image file with this name was selected." };
  try {
    return { kind: "result", result: await verifyLabel(image, row.application) };
  } catch (error) {
    return { kind: "error", message: (error as Error).message };
  }
}

export function BatchCheck() {
  const [rows, setRows] = useState<ManifestRow[]>([]);
  const [manifestNote, setManifestNote] = useState("");
  const [images, setImages] = useState<Map<string, File>>(new Map());
  const [run, setRun] = useState<Run | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState("");
  const [loadingExamples, setLoadingExamples] = useState(false);

  const running = run !== null && run.seconds === undefined;
  const busy = running || loadingExamples;
  const matched = rows.filter((row) => images.has(row.filename)).length;

  async function chooseManifest(file: File | undefined) {
    if (!file) return;
    setError("");
    setRun(null);
    try {
      const manifest = await parseManifest(file);
      setRows(manifest.rows);
      setManifestNote(
        `${manifest.rows.length} labels listed.` + (manifest.errors.length ? ` Skipped: ${manifest.errors.join(" ")}` : ""),
      );
    } catch (e) {
      setRows([]);
      setManifestNote("");
      setError((e as Error).message);
    }
  }

  function chooseImages(files: FileList | null) {
    setRun(null);
    setImages(new Map([...(files ?? [])].map((file) => [file.name, file])));
  }

  async function loadExamples() {
    setError("");
    setRun(null);
    setLoadingExamples(true);
    try {
      const manifest = await parseManifest(await fetchSample("batch.csv"));
      const files = await Promise.all(manifest.rows.map((row) => fetchSample(row.filename)));
      setRows(manifest.rows);
      setImages(new Map(files.map((file) => [file.name, file])));
      setManifestNote(`${manifest.rows.length} example labels loaded.`);
    } catch (e) {
      setError(`Could not load the examples. ${(e as Error).message}`);
    } finally {
      setLoadingExamples(false);
    }
  }

  async function checkAll() {
    if (busy) return;
    const batch = rows;
    const started = performance.now();
    setRun({ rows: batch, outcomes: batch.map(() => null) });
    let next = 0;
    async function worker() {
      while (next < batch.length) {
        const i = next++;
        const outcome = await checkOne(batch[i], images.get(batch[i].filename));
        setRun((r) => r && { ...r, outcomes: r.outcomes.with(i, outcome) });
      }
    }
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
    setRun((r) => r && { ...r, seconds: Math.round((performance.now() - started) / 1000) });
  }

  let imagesNote = "";
  if (images.size && rows.length) {
    const missing = rows.length - matched;
    imagesNote =
      `${images.size} images selected. ${matched} of ${rows.length} rows have a matching image.` +
      (missing ? ` ${missing} missing (they will be listed as errors).` : "");
  } else if (images.size) {
    imagesNote = `${images.size} images selected.`;
  }

  return (
    <div className="grid gap-6">
      <div className="grid gap-5 lg:grid-cols-2">
        <Step number={1} title="Application list (CSV)">
          <p className="mb-4 text-muted-foreground">
            One row per label. It needs a <code className="font-mono">filename</code> column plus any of:{" "}
            {APPLICATION_FIELDS.map((f) => f.key).join(", ")}.{" "}
            <a href="/samples/batch.csv" download className="font-semibold text-primary underline">
              Download an example CSV
            </a>
            .
          </p>
          <Label htmlFor="manifest" className="mb-2">
            CSV file
          </Label>
          <Input
            id="manifest"
            type="file"
            accept=".csv,text/csv"
            disabled={busy}
            onChange={(e) => chooseManifest(e.target.files?.[0])}
            className="h-auto"
          />
          {manifestNote && <p className="mt-3 text-muted-foreground">{manifestNote}</p>}
        </Step>
        <Step number={2} title="Label images">
          <p className="mb-4 text-muted-foreground">
            Select all the image files at once. File names must match the filename column.
          </p>
          <Label htmlFor="images" className="mb-2">
            Image files
          </Label>
          <Input
            id="images"
            type="file"
            accept="image/*"
            multiple
            disabled={busy}
            onChange={(e) => chooseImages(e.target.files)}
            className="h-auto"
          />
          {imagesNote && <p className="mt-3 text-muted-foreground">{imagesNote}</p>}
        </Step>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <Button size="lg" className="min-w-60" disabled={busy || matched === 0} onClick={checkAll}>
          {running && <LoaderCircle className="animate-spin" aria-hidden />}
          {running ? "Checking…" : "Check all labels"}
        </Button>
        <Button variant="link" className="text-lg underline" disabled={busy} onClick={loadExamples}>
          {loadingExamples ? "Loading the examples…" : "Load the example labels"}
        </Button>
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {run && <RunResults run={run} filter={filter} onFilter={setFilter} />}
    </div>
  );
}

function RunResults({ run, filter, onFilter }: { run: Run; filter: Filter; onFilter: (f: Filter) => void }) {
  const finished = run.outcomes.flatMap((outcome, i) => (outcome ? [{ i, row: run.rows[i], outcome }] : []));
  const counts: Record<Verdict, number> = { pass: 0, review: 0, fail: 0 };
  for (const { outcome } of finished) counts[verdictOf(outcome)]++;
  const shown = finished.filter(({ outcome }) => filter === "all" || verdictOf(outcome) === filter);
  const total = run.rows.length;

  return (
    <section aria-label="Results" className="grid gap-5">
      <div className="grid gap-2">
        <Progress value={(100 * finished.length) / total} aria-label="Labels checked" />
        <p aria-live="polite" className="text-muted-foreground">
          {run.seconds === undefined
            ? `Checked ${finished.length} of ${total}…`
            : `Done: ${total} labels in ${run.seconds} seconds.`}
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        {(["pass", "review", "fail"] as const).map((verdict) => (
          <StatusBadge
            key={verdict}
            look={{ ...VERDICT[verdict], word: `${counts[verdict]} ${VERDICT[verdict].count}` }}
            className="px-4 py-1.5 text-base"
          />
        ))}
      </div>

      <div role="group" aria-label="Show" className="flex flex-wrap gap-2">
        {FILTERS.map(([value, label]) => (
          <Button
            key={value}
            variant={filter === value ? "default" : "outline"}
            aria-pressed={filter === value}
            onClick={() => onFilter(value)}
            className="rounded-full border-2 px-5"
          >
            {label}
          </Button>
        ))}
      </div>

      <div className="overflow-hidden rounded-xl border bg-card">
        <Table className="max-md:[&_tbody_tr]:block max-md:[&_td]:block max-md:[&_td]:py-1.5 max-md:[&_thead]:hidden">
          <TableHeader>
            <TableRow>
              <TableHead>Label</TableHead>
              <TableHead>{IDENTIFYING_FIELD.label}</TableHead>
              <TableHead>Result</TableHead>
              <TableHead>Issues</TableHead>
              <TableHead>
                <span className="sr-only">Details</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map(({ i, row, outcome }) => (
              <BatchRow key={i} row={row} outcome={outcome} />
            ))}
            {shown.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground">
                  No labels here yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}

function BatchRow({ row, outcome }: { row: ManifestRow; outcome: Outcome }) {
  const [open, setOpen] = useState(false);
  const look = outcome.kind === "error" ? { ...VERDICT.fail, word: "Error" } : VERDICT[outcome.result.overall];
  return (
    <>
      <TableRow className="max-md:py-2">
        <TableCell className="font-semibold [overflow-wrap:anywhere] md:whitespace-nowrap">{row.filename}</TableCell>
        <TableCell>{row.application[IDENTIFYING_FIELD.key]}</TableCell>
        <TableCell>
          <StatusBadge look={look} />
        </TableCell>
        <TableCell className="text-muted-foreground">{issues(outcome)}</TableCell>
        <TableCell>
          {outcome.kind === "result" && (
            <Button variant="outline" aria-expanded={open} onClick={() => setOpen(!open)} className="border-2">
              {open ? "Hide" : "Details"}
            </Button>
          )}
        </TableCell>
      </TableRow>
      {open && outcome.kind === "result" && (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={5} className="bg-muted/40 p-4">
            <ResultView result={outcome.result} />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}
