import type { QueueItem } from "./api";

export function oldestFirst(items: QueueItem[]): QueueItem[] {
  return [...items].sort((a, b) => a.submitted_at.localeCompare(b.submitted_at) || a.id.localeCompare(b.id));
}

export const applicationHref = (id: string) => `/applications/${encodeURIComponent(id)}`;

// Dates arrive as plain YYYY-MM-DD; read them as UTC so no time zone shifts the day.
const DATE = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

export const formatDate = (isoDate: string) => DATE.format(new Date(`${isoDate}T00:00:00Z`));
