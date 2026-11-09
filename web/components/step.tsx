import type { ReactNode } from "react";
import { Card } from "@/components/ui/card";

export function Step({ number, title, children }: { number: number; title: string; children: ReactNode }) {
  return (
    <Card className="min-w-0 gap-0 p-5">
      <h2 className="mb-4 flex items-center gap-3 text-xl font-bold">
        <span
          aria-hidden
          className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-base text-primary-foreground"
        >
          {number}
        </span>
        <span>
          <span className="sr-only">Step {number}: </span>
          {title}
        </span>
      </h2>
      {children}
    </Card>
  );
}
