import { proxyToChecker } from "@/lib/checker";

export async function POST(request: Request, { params }: RouteContext<"/api/queue/[id]/check">) {
  const { id } = await params;
  return proxyToChecker(request, `/api/queue/${encodeURIComponent(id)}/check`);
}
