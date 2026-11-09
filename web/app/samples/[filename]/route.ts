import { proxyToChecker } from "@/lib/checker";

export async function GET(request: Request, { params }: RouteContext<"/samples/[filename]">) {
  const { filename } = await params;
  return proxyToChecker(request, `/samples/${encodeURIComponent(filename)}`);
}
