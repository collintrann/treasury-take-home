import { Suspense } from "react";
import type { Metadata } from "next";
import { ReviewScreen } from "@/components/review-screen";

export const metadata: Metadata = { title: "Application review" };

export default function ApplicationPage() {
  return (
    <Suspense>
      <ReviewScreen />
    </Suspense>
  );
}
