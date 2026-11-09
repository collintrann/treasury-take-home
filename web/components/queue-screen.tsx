"use client";

import Link from "next/link";
import { ChevronRight, LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorNotice } from "@/components/error-notice";
import { DECISION, NOT_CHECKED, STATUS, StatusBadge, StatusText } from "@/components/status";
import { getQueue, type QueueItem } from "@/lib/api";
import { PRODUCT_TYPES } from "@/lib/fields";
import { applicationHref, formatDate, oldestFirst } from "@/lib/queue";
import { useReviews, type Review } from "@/lib/reviews";
import { useLoad } from "@/lib/use-load";

type Reviews = Record<string, Review>;

export function QueueScreen() {
  const { state, retry } = useLoad(getQueue);
  const reviews = useReviews();

  return (
    <div className="grid gap-6">
      <div className="grid gap-2">
        <h1 className="text-4xl font-bold max-sm:text-3xl">Review queue</h1>
        <p className="text-lg text-muted-foreground">
          Open an application to check its label against what the applicant submitted.
        </p>
      </div>

      {state.kind === "loading" && <QueueSkeleton />}
      {state.kind === "error" && <ErrorNotice title="The queue didn't load" message={state.message} onRetry={retry} />}
      {state.kind === "ready" &&
        (state.data.length === 0 ? (
          <Card className="px-6 text-xl">No applications are waiting for review.</Card>
        ) : (
          <>
            <Summary items={state.data} reviews={reviews} />
            <QueueTable items={oldestFirst(state.data)} reviews={reviews} />
          </>
        ))}
    </div>
  );
}

function Summary({ items, reviews }: { items: QueueItem[]; reviews: Reviews }) {
  const checked = items.filter((item) => reviews[item.id]?.check.kind === "done").length;
  const decided = items.filter((item) => reviews[item.id]?.decision).length;
  const counts = [
    { label: items.length === 1 ? "application" : "applications", value: items.length },
    { label: "not checked yet", value: items.length - checked },
    { label: "checked", value: checked },
    { label: "decided", value: decided },
  ];
  return (
    <Card className="px-5 py-4">
      <ul aria-label="Queue summary" className="grid grid-cols-2 gap-x-4 gap-y-2 text-lg max-sm:text-base sm:flex sm:flex-wrap sm:gap-x-10">
        {counts.map(({ label, value }) => (
          <li key={label}>
            <span className="text-2xl font-bold tabular-nums">{value}</span> {label}
          </li>
        ))}
      </ul>
    </Card>
  );
}

// Below the md breakpoint each row becomes a stacked card, and `order` moves
// the brand to the top.
const CELL = "px-3 py-4 align-middle max-md:p-0";

function QueueTable({ items, reviews }: { items: QueueItem[]; reviews: Reviews }) {
  return (
    <Table className="text-lg max-md:block [&_tbody]:max-md:grid [&_tbody]:max-md:gap-3">
      <TableCaption className="sr-only">Applications waiting for review, oldest first</TableCaption>
      <TableHeader className="max-md:hidden [&_tr]:border-b-2 [&_tr]:border-foreground/20">
        <TableRow className="hover:bg-transparent">
          <TableHead scope="col">Application</TableHead>
          <TableHead scope="col">Brand</TableHead>
          <TableHead scope="col">Applicant</TableHead>
          <TableHead scope="col">Beverage type</TableHead>
          <TableHead scope="col">Submitted</TableHead>
          <TableHead scope="col">Status</TableHead>
          <TableHead aria-hidden />
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => {
          const type = PRODUCT_TYPES[item.product_type];
          return (
            <TableRow
              key={item.id}
              className={cn(
                "group relative hover:bg-muted",
                "max-md:flex max-md:flex-wrap max-md:items-center max-md:gap-x-5 max-md:gap-y-1.5 max-md:rounded-xl max-md:border max-md:bg-card max-md:p-4",
              )}
            >
              <TableCell className={cn(CELL, "max-md:order-4 max-md:text-base")}>
                <Link
                  href={applicationHref(item.id)}
                  className={cn(
                    "font-bold whitespace-nowrap text-primary tabular-nums underline underline-offset-4 outline-none",
                    "after:absolute after:inset-0 after:rounded-xl focus-visible:after:outline-3 focus-visible:after:-outline-offset-3 focus-visible:after:outline-foreground",
                  )}
                >
                  {item.id}
                </Link>
              </TableCell>
              <TableCell className={cn(CELL, "font-bold max-md:order-1 max-md:basis-full max-md:text-xl")}>
                {item.brand_name}
              </TableCell>
              <TableCell className={cn(CELL, "max-md:order-2 max-md:basis-full")}>{item.applicant}</TableCell>
              <TableCell className={cn(CELL, "max-md:order-3 max-md:basis-full max-md:pt-1")}>
                <Badge variant="secondary" className="font-normal">
                  <type.Icon aria-hidden />
                  {type.label}
                </Badge>
              </TableCell>
              <TableCell className={cn(CELL, "whitespace-nowrap tabular-nums max-md:order-5 max-md:text-base")}>
                {formatDate(item.submitted_at)}
              </TableCell>
              <TableCell className={cn(CELL, "max-md:order-6 max-md:basis-full max-md:pt-2")}>
                <QueueStatus review={reviews[item.id]} />
              </TableCell>
              <TableCell aria-hidden className={cn(CELL, "max-md:hidden")}>
                <ChevronRight className="size-6 text-muted-foreground group-hover:text-foreground" />
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

function QueueStatus({ review }: { review: Review | undefined }) {
  const check = review?.check;
  const decision = review?.decision;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {check?.kind === "done" ? (
        <StatusBadge look={STATUS[check.result.overall]} />
      ) : check?.kind === "checking" ? (
        <span className="inline-flex items-center gap-2 text-muted-foreground">
          <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden />
          Checking…
        </span>
      ) : (
        <StatusText look={NOT_CHECKED} />
      )}
      {decision && <StatusText look={DECISION[decision]} prefix="Decision:" />}
    </div>
  );
}

function QueueSkeleton() {
  return (
    <div aria-busy className="grid gap-3">
      <p className="sr-only" role="status">
        Loading applications…
      </p>
      <Skeleton className="h-16 rounded-xl" />
      {Array.from({ length: 6 }, (_, i) => (
        <Skeleton key={i} className="h-14 rounded-lg" />
      ))}
    </div>
  );
}
