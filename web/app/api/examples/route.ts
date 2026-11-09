import { proxyToChecker } from "@/lib/checker";

export function GET(request: Request) {
  return proxyToChecker(request, "/api/examples");
}
