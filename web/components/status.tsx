import { CircleCheck, CircleMinus, CircleX, TriangleAlert, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { FieldStatus, Verdict } from "@/lib/api";

type Tone = "pass" | "review" | "fail" | "skip";

export const TONE: Record<Tone, { fill: string; edge: string }> = {
  pass: { fill: "bg-pass-bg text-pass border-pass", edge: "border-l-pass" },
  review: { fill: "bg-review-bg text-review border-review", edge: "border-l-review" },
  fail: { fill: "bg-fail-bg text-fail border-fail", edge: "border-l-fail" },
  skip: { fill: "bg-skip-bg text-skip border-skip", edge: "border-l-skip" },
};

export interface StatusLook {
  Icon: LucideIcon;
  word: string;
  tone: Tone;
}

export const FIELD_STATUS: Record<FieldStatus, StatusLook> = {
  pass: { Icon: CircleCheck, word: "Match", tone: "pass" },
  review: { Icon: TriangleAlert, word: "Check", tone: "review" },
  fail: { Icon: CircleX, word: "Mismatch", tone: "fail" },
  missing: { Icon: CircleX, word: "Not found", tone: "fail" },
  skipped: { Icon: CircleMinus, word: "Skipped", tone: "skip" },
};

export const VERDICT: Record<Verdict, StatusLook & { title: string; detail: string; count: string }> = {
  pass: {
    Icon: CircleCheck,
    word: "Pass",
    tone: "pass",
    title: "Label matches the application",
    detail: "Every checked item matches.",
    count: "passed",
  },
  review: {
    Icon: TriangleAlert,
    word: "Review",
    tone: "review",
    title: "Needs your review",
    detail: "Nothing is clearly wrong, but some items need a human eye.",
    count: "need review",
  },
  fail: {
    Icon: CircleX,
    word: "Problems",
    tone: "fail",
    title: "Problems found",
    detail: "At least one item does not match. See the items marked below.",
    count: "problems",
  },
};

export function StatusBadge({ look, className }: { look: StatusLook; className?: string }) {
  return (
    <Badge variant="outline" className={cn("border-2", TONE[look.tone].fill, className)}>
      <look.Icon aria-hidden />
      {look.word}
    </Badge>
  );
}
