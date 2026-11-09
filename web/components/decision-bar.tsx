"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { DECISION, StatusBadge, TONE } from "@/components/status";
import { decide, type Decision } from "@/lib/reviews";

const CHOICES = Object.keys(DECISION) as Decision[];

interface Props {
  id: string;
  decision: Decision | null;
  nextHref: string;
  className?: string;
}

export function DecisionBar({ id, decision, nextHref, className }: Props) {
  const [confirming, setConfirming] = useState<Decision | null>(null);

  function record(choice: Decision | null) {
    decide(id, choice);
    setConfirming(null);
  }

  return (
    <Card
      role="region"
      aria-labelledby="decision-title"
      className={cn(
        "max-sm:sticky max-sm:bottom-0 max-sm:z-10 -mx-4 gap-2 rounded-none border-t-2 border-foreground/15 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] ring-0",
        "sm:mx-0 sm:gap-3 sm:rounded-xl sm:border-2 sm:p-5",
        className,
      )}
    >
      <h2 id="decision-title" className="text-xl font-bold max-sm:sr-only">
        Your decision
      </h2>

      {decision ? (
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge look={DECISION[decision]} className="min-h-10 px-4 text-lg" />
          <Button variant="outline" onClick={() => record(null)}>
            Change decision
          </Button>
          <Button asChild size="lg" className="sm:ml-auto">
            <Link href={nextHref}>
              {nextHref === "/" ? "Back to the queue" : "Next application"}
              <ChevronRight aria-hidden />
            </Link>
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2 sm:gap-3">
          {CHOICES.map((choice) => {
            const look = DECISION[choice];
            return (
              <Button
                key={choice}
                size="lg"
                variant="ghost"
                onClick={() => setConfirming(choice)}
                className={cn(
                  "h-auto border-2 bg-card px-2 sm:px-3",
                  "max-sm:min-h-14 max-sm:text-base max-sm:leading-tight max-sm:whitespace-normal max-sm:[&_svg]:hidden",
                  TONE[look.tone].button,
                )}
              >
                <look.Icon aria-hidden />
                {look.action}
              </Button>
            );
          })}
        </div>
      )}

      <Separator className="max-sm:hidden" />
      <p className="text-muted-foreground max-sm:text-sm">This tool supports your review. You make the decision.</p>

      <Dialog open={confirming !== null} onOpenChange={(open) => !open && setConfirming(null)}>
        {confirming && (
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{DECISION[confirming].question}</DialogTitle>
              <DialogDescription>Application {id}. You can change this later.</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose asChild>
                <Button size="lg" variant="outline">
                  Cancel
                </Button>
              </DialogClose>
              <Button size="lg" onClick={() => record(confirming)}>
                {DECISION[confirming].confirm}
              </Button>
            </DialogFooter>
          </DialogContent>
        )}
      </Dialog>
    </Card>
  );
}
