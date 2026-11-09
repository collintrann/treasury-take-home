"use client";

import { useEffect, useState } from "react";
import { ImageOff, LoaderCircle, RotateCw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorNotice } from "@/components/error-notice";
import { Findings } from "@/components/findings";
import { STATUS, VERDICT } from "@/components/status";
import type { CheckResult } from "@/lib/api";
import type { CheckState } from "@/lib/reviews";

export function CheckPanel({ state, onRun }: { state: CheckState; onRun: () => void }) {
  switch (state.kind) {
    case "idle":
    case "checking":
      return <Checking startedAt={state.kind === "checking" ? state.startedAt : null} />;
    case "error":
      return <ErrorNotice title="The check didn't finish" message={state.message} onRetry={onRun} />;
    case "done":
      return <CheckOutcome result={state.result} onRecheck={onRun} />;
  }
}

// Checks usually take 3 to 10 seconds. The bar eases toward full without ever
// claiming to be done, so a slow check never looks stuck at 100%.
const EASE_SECONDS = 4;

function Checking({ startedAt }: { startedAt: number | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(timer);
  }, []);
  const seconds = startedAt === null ? 0 : Math.max(0, (now - startedAt) / 1000);
  const percent = 95 * (1 - Math.exp(-seconds / EASE_SECONDS));

  return (
    <div className="grid gap-4">
      <Card className="gap-4 border-2 border-primary/40 py-6 ring-0">
        <CardHeader className="flex items-center gap-3 px-6">
          <LoaderCircle className="size-8 shrink-0 animate-spin text-primary motion-reduce:animate-none" aria-hidden />
          <CardTitle role="status" className="text-2xl font-bold">
            Checking the label…
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 px-6">
          <Progress value={percent} aria-label="Check progress" className="h-3" />
          <p className="text-muted-foreground">
            Comparing the label with the application and the government warning. This usually takes 3 to 10 seconds.
          </p>
        </CardContent>
      </Card>
      <div aria-hidden className="grid gap-3">
        <Skeleton className="h-16 rounded-xl" />
        <Skeleton className="h-16 rounded-xl" />
      </div>
    </div>
  );
}

function CheckOutcome({ result, onRecheck }: { result: CheckResult; onRecheck: () => void }) {
  const look = STATUS[result.overall];
  return (
    <div className="grid gap-5">
      <Alert
        variant={look.tone}
        role="status"
        aria-labelledby="verdict-title"
        className="gap-y-1 p-5 *:[svg]:size-12! sm:p-6"
      >
        <look.Icon aria-hidden />
        <AlertTitle id="verdict-title" className="text-4xl leading-tight max-sm:text-3xl">
          <span className="sr-only">Check result: </span>
          {look.word}
        </AlertTitle>
        <AlertDescription className="grid gap-3">
          <p className="text-lg">{VERDICT[result.overall]}</p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="text-muted-foreground">Checked in {(result.elapsed_ms / 1000).toFixed(1)} seconds</span>
            <Button variant="outline" onClick={onRecheck}>
              <RotateCw aria-hidden />
              Check again
            </Button>
          </div>
        </AlertDescription>
      </Alert>

      {!result.image_assessable && (
        <Alert variant="review" role="note">
          <ImageOff aria-hidden />
          <AlertTitle>This image can&apos;t be reliably assessed. Request a clearer image.</AlertTitle>
          {result.image_note && <AlertDescription>{result.image_note}</AlertDescription>}
        </Alert>
      )}

      <Findings findings={result.findings} />
    </div>
  );
}
