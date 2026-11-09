"use client";

import { useCallback, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { CheckPanel } from "@/components/check-panel";
import { DecisionBar } from "@/components/decision-bar";
import { ErrorNotice } from "@/components/error-notice";
import { LabelPanels } from "@/components/label-panels";
import { getApplication, getQueue, type QueueItem, type QueuedApplication } from "@/lib/api";
import { APPLICATION_FIELDS, PRODUCT_TYPES } from "@/lib/fields";
import { applicationHref, formatDate, oldestFirst } from "@/lib/queue";
import { checkIfNew, runCheck, useReview } from "@/lib/reviews";
import { useLoad } from "@/lib/use-load";

export function ReviewScreen() {
  const { id } = useParams<{ id: string }>();
  // Keyed so moving to another application starts from a clean screen.
  return <Review key={id} id={decodeURIComponent(id)} />;
}

function Review({ id }: { id: string }) {
  const review = useReview(id);
  const load = useCallback(() => Promise.all([getApplication(id), getQueue()]), [id]);
  const { state, retry } = useLoad(load);

  useEffect(() => checkIfNew(id), [id]);

  if (state.kind === "loading") return <ReviewSkeleton />;
  if (state.kind === "error") {
    return (
      <div className="grid gap-6">
        <BackLink />
        <ErrorNotice title="This application didn't open" message={state.message} onRetry={retry} />
      </div>
    );
  }

  const [application, queue] = state.data;
  const order = oldestFirst(queue);
  const index = order.findIndex((item) => item.id === id);
  const previous = order[index - 1];
  const next = order[index + 1];

  return (
    <div className="grid gap-6 lg:gap-8">
      <nav aria-label="Applications" className="flex flex-wrap items-center justify-between gap-3">
        <BackLink />
        <div className="flex items-center gap-2">
          <StepLink target={previous} direction="previous" />
          {index >= 0 && (
            <span className="px-2 text-muted-foreground tabular-nums">
              {index + 1} of {order.length}
            </span>
          )}
          <StepLink target={next} direction="next" />
        </div>
      </nav>

      <ApplicationHeader application={application} />

      {/* DOM order is check, then what was submitted, then the decision, so on
          small screens the verdict comes first and the decision bar stays
          pinned to the bottom of the whole page. */}
      <div className="grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:grid-rows-[auto_1fr]">
        <section aria-label="Check" className="grid content-start gap-6 lg:col-start-2">
          <CheckPanel state={review.check} onRun={() => runCheck(id)} />
        </section>

        <div className="grid content-start gap-8 lg:col-start-1 lg:row-span-2 lg:row-start-1">
          <section aria-labelledby="label-title" className="grid gap-3">
            <h2 id="label-title" className="text-2xl font-bold">
              Label
            </h2>
            <LabelPanels images={application.images} brand={application.application.brand_name || id} />
          </section>
          <ApplicationDetails application={application} />
        </div>

        <DecisionBar
          id={id}
          decision={review.decision}
          nextHref={next ? applicationHref(next.id) : "/"}
          className="self-start lg:col-start-2 lg:row-start-2"
        />
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Button asChild variant="ghost" className="-ml-3 text-lg">
      <Link href="/">
        <ArrowLeft className="size-5" aria-hidden />
        Review queue
      </Link>
    </Button>
  );
}

function StepLink({ target, direction }: { target: QueueItem | undefined; direction: "previous" | "next" }) {
  const label = direction === "previous" ? "Previous" : "Next";
  const content = (
    <>
      {direction === "previous" && <ChevronLeft className="size-5" aria-hidden />}
      {label}
      {direction === "next" && <ChevronRight className="size-5" aria-hidden />}
    </>
  );
  if (!target) {
    return (
      <Button variant="outline" disabled>
        {content}
      </Button>
    );
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button asChild variant="outline">
          <Link href={applicationHref(target.id)}>{content}</Link>
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {target.id}, {target.brand_name}
      </TooltipContent>
    </Tooltip>
  );
}

function ApplicationHeader({ application }: { application: QueuedApplication }) {
  const type = PRODUCT_TYPES[application.product_type];
  return (
    <header className="grid gap-3">
      <h1 className="text-4xl font-bold tabular-nums max-sm:text-3xl">{application.id}</h1>
      <dl className="flex flex-wrap items-center gap-x-8 gap-y-2 text-lg">
        <div className="flex items-baseline gap-2">
          <dt className="text-muted-foreground">Applicant</dt>
          <dd className="font-bold">{application.applicant}</dd>
        </div>
        <div className="flex items-center gap-2">
          <dt className="sr-only">Beverage type</dt>
          <dd>
            <Badge variant="secondary" className="text-lg font-normal">
              <type.Icon aria-hidden />
              {type.label}
            </Badge>
          </dd>
        </div>
        <div className="flex items-baseline gap-2">
          <dt className="text-muted-foreground">Submitted</dt>
          <dd className="font-bold tabular-nums">{formatDate(application.submitted_at)}</dd>
        </div>
      </dl>
    </header>
  );
}

function ApplicationDetails({ application }: { application: QueuedApplication }) {
  return (
    <Card className="gap-4 py-5">
      <CardHeader className="px-5">
        <CardTitle className="text-2xl font-bold">
          <h2>Application</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="px-5">
        <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
          {APPLICATION_FIELDS.map((field) => {
            const value = application.application[field.key];
            return (
              <div
                key={field.key}
                className={cn("grid content-start gap-0.5", field.key === "producer_name_address" && "sm:col-span-2")}
              >
                <dt className="text-muted-foreground">{field.label}</dt>
                <dd className={cn("text-lg break-words", !value && "text-muted-foreground italic")}>
                  {value || "Not provided"}
                </dd>
              </div>
            );
          })}
        </dl>
      </CardContent>
    </Card>
  );
}

function ReviewSkeleton() {
  return (
    <div aria-busy className="grid gap-8">
      <p className="sr-only" role="status">
        Loading the application…
      </p>
      <Skeleton className="h-11 w-48" />
      <div className="grid gap-3">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-7 w-full max-w-xl" />
      </div>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <Skeleton className="h-[min(60dvh,36rem)] rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
      </div>
    </div>
  );
}
