import { proxyToChecker } from "@/lib/checker";

export async function GET(request: Request, { params }: RouteContext<"/api/queue/[id]">) {
  const { id } = await params;
  return proxyToChecker(request, `/api/queue/${encodeURIComponent(id)}`);
}
