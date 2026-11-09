import { UNREACHABLE } from "./api";

// Forwards a browser request to the checker service so the browser only ever
// talks to this app and the shared secret stays on the server.
export async function proxyToChecker(request: Request, path: string): Promise<Response> {
  const headers = new Headers({ "X-Checker-Secret": process.env.CHECKER_SECRET ?? "" });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  let upstream: Response;
  try {
    upstream = await fetch(new URL(path, process.env.CHECKER_URL), {
      method: request.method,
      headers,
      body: request.body,
      // Required by Node to send a streamed request body.
      duplex: "half",
      cache: "no-store",
    } as RequestInit);
  } catch (error) {
    console.error(`checker request to ${path} failed`, error);
    return Response.json({ detail: UNREACHABLE }, { status: 502 });
  }

  const responseHeaders = new Headers();
  for (const name of ["content-type", "cache-control"]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}
