import { Fragment } from "react";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { FIELD_STATUS, StatusBadge, TONE, VERDICT } from "@/components/status";
import { isApplicationField } from "@/lib/fields";
import type { DiffPart, FieldResult, VerificationResult } from "@/lib/api";

export function ResultView({ result }: { result: VerificationResult }) {
  const verdict = VERDICT[result.overall];
  return (
    <div className="grid gap-4">
      <div role="status" className={cn("flex items-center gap-4 rounded-xl border-2 p-5", TONE[verdict.tone].fill)}>
        <verdict.Icon className="size-11 shrink-0" aria-hidden />
        <div>
          <h2 className="text-2xl font-bold">{verdict.title}</h2>
          <p className="text-foreground">{verdict.detail}</p>
        </div>
      </div>
      <p className="text-muted-foreground">
        Checked in {(result.elapsed_ms / 1000).toFixed(1)} seconds.
        {result.extraction_note && ` ${result.extraction_note}`}
      </p>
      <ul className="grid gap-3">
        {result.fields.map((field) => (
          <li key={field.field}>
            <FieldCard field={field} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function FieldCard({ field }: { field: FieldResult }) {
  const look = FIELD_STATUS[field.status];
  return (
    <Card className={cn("gap-2 border-l-8 px-5 py-4", TONE[look.tone].edge)}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h3 className="text-lg font-bold">{field.label}</h3>
        <StatusBadge look={look} />
      </div>
      {field.note && <p>{field.note}</p>}
      <FieldDetail field={field} />
    </Card>
  );
}

function FieldDetail({ field }: { field: FieldResult }) {
  if (field.status === "skipped") return null;
  if (field.diff) return field.diff.some((part) => part.op !== "equal") ? <WordDiff diff={field.diff} /> : null;
  // Only application fields have an application value to compare with.
  if (!isApplicationField(field.field)) return null;
  return (
    <div className="mt-1 grid gap-3 sm:grid-cols-2">
      <Compared heading="Application" value={field.expected} empty="(blank)" />
      <Compared heading="On the label" value={field.found} empty="Not found" />
    </div>
  );
}

function Compared({ heading, value, empty }: { heading: string; value: string | null; empty: string }) {
  return (
    <div className="rounded-lg bg-muted px-3 py-2 break-words">
      <div className="text-sm font-bold tracking-wide text-muted-foreground uppercase">{heading}</div>
      {value || <em className="text-muted-foreground">{empty}</em>}
    </div>
  );
}

const MISSING = "bg-fail-bg px-0.5 text-fail line-through decoration-2";
const EXTRA = "bg-review-bg px-0.5 text-review underline decoration-2 underline-offset-2";

function WordDiff({ diff }: { diff: DiffPart[] }) {
  return (
    <div className="mt-1 grid gap-2">
      <p className="rounded-lg bg-muted px-3 py-2 leading-relaxed break-words">
        {diff.map((part, i) => (
          <Fragment key={i}>
            {i > 0 && " "}
            {part.op === "equal" && part.text}
            {part.op === "missing" && (
              <del title="Required but missing" className={MISSING}>
                {part.text}
              </del>
            )}
            {part.op === "extra" && (
              <ins title="On the label but not in the required text" className={EXTRA}>
                {part.text}
              </ins>
            )}
          </Fragment>
        ))}
      </p>
      <p className="text-sm text-muted-foreground">
        <del className={MISSING}>Struck out</del> = required wording missing from the label.{" "}
        <ins className={EXTRA}>Underlined</ins> = wording on the label that shouldn&apos;t be there.
      </p>
    </div>
  );
}
