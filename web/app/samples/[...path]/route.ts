import { proxyToChecker } from "@/lib/checker";

export async function GET(request: Request, { params }: RouteContext<"/samples/[...path]">) {
  const { path } = await params;
  return proxyToChecker(request, `/samples/${path.map(encodeURIComponent).join("/")}`);
}
