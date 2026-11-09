import {
  Ban,
  CircleCheck,
  CircleDashed,
  CircleMinus,
  CircleX,
  FilePen,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { FindingStatus, Overall } from "@/lib/api";
import type { Decision } from "@/lib/reviews";

// Every status is shown as an icon and a word, never by color alone.

export type Tone = "pass" | "review" | "fail" | "neutral";

// Tone names match the Badge and Alert variants of the same name.
export const TONE: Record<Tone, { text: string; edge: string; button: string }> = {
  pass: { text: "text-pass", edge: "border-l-pass", button: "border-pass text-pass hover:bg-pass-bg hover:text-pass" },
  review: {
    text: "text-review",
    edge: "border-l-review",
    button: "border-review text-review hover:bg-review-bg hover:text-review",
  },
  fail: { text: "text-fail", edge: "border-l-fail", button: "border-fail text-fail hover:bg-fail-bg hover:text-fail" },
  neutral: { text: "text-skip", edge: "border-l-skip", button: "border-skip text-skip hover:bg-skip-bg hover:text-skip" },
};

export interface Look {
  Icon: LucideIcon;
  word: string;
  tone: Tone;
}

export const STATUS: Record<FindingStatus, Look & { group: string }> = {
  fail: {
    Icon: CircleX,
    word: "Fail",
    tone: "fail",
    group: "Failed",
  },
  needs_review: {
    Icon: TriangleAlert,
    word: "Needs review",
    tone: "review",
    group: "Needs review",
  },
  pass: {
    Icon: CircleCheck,
    word: "Pass",
    tone: "pass",
    group: "Passed",
  },
  not_evaluated: {
    Icon: CircleMinus,
    word: "Not evaluated",
    tone: "neutral",
    group: "Not evaluated",
  },
};

export const NOT_CHECKED: Look = { Icon: CircleDashed, word: "Not checked yet", tone: "neutral" };

export const DECISION: Record<Decision, Look & { action: string; question: string; confirm: string }> = {
  approve: { Icon: CircleCheck, word: "Approved", tone: "pass", action: "Approve", question: "Approve this application?", confirm: "Yes, approve" },
  needs_correction: {
    Icon: FilePen,
    word: "Needs correction",
    tone: "review",
    action: "Needs correction",
    question: "Send this application back for correction?",
    confirm: "Yes, needs correction",
  },
  reject: { Icon: Ban, word: "Rejected", tone: "fail", action: "Reject", question: "Reject this application?", confirm: "Yes, reject" },
};

export const VERDICT: Record<Overall, string> = {
  fail: "At least one item fails. The problems are listed first.",
  needs_review: "Nothing clearly fails, but some items need your judgment.",
  pass: "Everything checked matches the application and the warning rules.",
};

export function StatusBadge({ look, className }: { look: Look; className?: string }) {
  return (
    <Badge variant={look.tone} className={className}>
      <look.Icon aria-hidden />
      {look.word}
    </Badge>
  );
}

export function StatusText({ look, prefix }: { look: Look; prefix?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <look.Icon className={cn("size-5 shrink-0", TONE[look.tone].text)} aria-hidden />
      {prefix && <span className="text-muted-foreground">{prefix}</span>}
      <span className={cn(look.tone === "neutral" ? "text-muted-foreground" : "font-bold")}>{look.word}</span>
    </span>
  );
}
