"use client";

import { Fragment } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";
import { STATUS, StatusBadge, TONE } from "@/components/status";
import type { DiffPart, Finding, FindingGroup, FindingStatus } from "@/lib/api";

const SECTIONS: readonly { status: FindingStatus; open: boolean }[] = [
  { status: "fail", open: true },
  { status: "needs_review", open: true },
  { status: "pass", open: false },
  { status: "not_evaluated", open: false },
];

const GROUP: Record<FindingGroup, { name: string; expected: string }> = {
  application: { name: "Application field", expected: "Application" },
  warning: { name: "Government warning", expected: "Required" },
};

const GROUP_ORDER: readonly FindingGroup[] = ["application", "warning"];

export function Findings({ findings }: { findings: Finding[] }) {
  return (
    <div className="grid gap-4">
      {SECTIONS.map(({ status, open }) => {
        const items = findings
          .filter((f) => f.status === status)
          .sort((a, b) => GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group));
        if (items.length === 0) return null;
        const look = STATUS[status];
        return (
          <Collapsible key={status} defaultOpen={open} asChild>
            <Card className="gap-0 py-0">
              <h3>
                <CollapsibleTrigger
                  className={cn(
                    "group flex min-h-16 w-full items-center gap-3 rounded-xl px-5 py-3 text-left text-xl font-bold",
                    "hover:bg-muted focus-visible:outline-3 focus-visible:-outline-offset-3 focus-visible:outline-foreground",
                  )}
                >
                  <ChevronRight
                    className="size-5 shrink-0 transition-transform group-data-[state=open]:rotate-90 motion-reduce:transition-none"
                    aria-hidden
                  />
                  <look.Icon className={cn("size-6 shrink-0", TONE[look.tone].text)} aria-hidden />
                  {look.group}
                  <Badge variant="secondary" className="ml-auto tabular-nums">
                    {items.length}
                    <span className="sr-only">{items.length === 1 ? " item" : " items"}</span>
                  </Badge>
                </CollapsibleTrigger>
              </h3>
              <CollapsibleContent>
                <ul className="px-5 pb-5">
                  {items.map((finding, i) => (
                    <li key={finding.key}>
                      {i > 0 && <Separator className="my-5" />}
                      <FindingItem finding={finding} />
                    </li>
                  ))}
                </ul>
              </CollapsibleContent>
            </Card>
          </Collapsible>
        );
      })}
    </div>
  );
}

function FindingItem({ finding }: { finding: Finding }) {
  const look = STATUS[finding.status];
  const changed = finding.diff?.some((part) => part.op !== "equal");
  const compared = finding.expected !== null || finding.observed !== null;
  return (
    <article className={cn("grid gap-3 border-l-6 pl-4", TONE[look.tone].edge)}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <p className="text-muted-foreground">{GROUP[finding.group].name}</p>
          <h4 className="text-lg font-bold">{finding.label}</h4>
        </div>
        <StatusBadge look={look} />
      </div>
      {finding.explanation && <p>{finding.explanation}</p>}
      {changed && finding.diff ? (
        <WordDiff diff={finding.diff} />
      ) : (
        compared && (
          <dl className="grid gap-3 sm:grid-cols-2">
            <Value heading={GROUP[finding.group].expected} value={finding.expected} empty="Left blank" />
            <Value
              heading="On the label"
              value={finding.observed}
              empty={finding.status === "not_evaluated" ? "Not evaluated" : "Not found on the label"}
            />
          </dl>
        )
      )}
    </article>
  );
}

function Value({ heading, value, empty }: { heading: string; value: string | null; empty: string }) {
  return (
    <div className="grid content-start gap-1 rounded-lg bg-muted px-4 py-3">
      <dt className="text-muted-foreground">{heading}</dt>
      <dd className="text-lg break-words">{value || <em className="text-muted-foreground">{empty}</em>}</dd>
    </div>
  );
}

const MISSING = "rounded-sm bg-fail-bg px-1 text-fail line-through decoration-2";
const EXTRA = "rounded-sm bg-review-bg px-1 text-review underline decoration-2 underline-offset-4";

function WordDiff({ diff }: { diff: DiffPart[] }) {
  return (
    <div className="grid gap-2">
      <p className="rounded-lg bg-muted px-4 py-3 text-lg leading-relaxed break-words">
        {diff.map((part, i) => (
          <Fragment key={i}>
            {i > 0 && " "}
            {part.op === "equal" && part.text}
            {part.op === "missing" && (
              <del className={MISSING}>
                <span className="sr-only">Missing from the label: </span>
                {part.text}
              </del>
            )}
            {part.op === "extra" && (
              <ins className={EXTRA}>
                <span className="sr-only">Should not be on the label: </span>
                {part.text}
              </ins>
            )}
          </Fragment>
        ))}
      </p>
      <ul aria-hidden className="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground">
        <li>
          <del className={MISSING}>Struck out</del> required wording missing from the label
        </li>
        <li>
          <ins className={EXTRA}>Underlined</ins> wording on the label that shouldn&apos;t be there
        </li>
      </ul>
    </div>
  );
}
