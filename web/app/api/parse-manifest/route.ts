import { proxyToChecker } from "@/lib/checker";

export function POST(request: Request) {
  return proxyToChecker(request, "/api/parse-manifest");
}
