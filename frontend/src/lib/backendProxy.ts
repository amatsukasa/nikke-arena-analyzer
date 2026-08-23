import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const CHAMPION_PROXY_MAX_BODY_BYTES = 100 * 1024 * 1024;

async function readBoundedBody(request: NextRequest) {
  const declared = request.headers.get("content-length");
  if (declared && (!/^\d+$/.test(declared) || Number(declared) > CHAMPION_PROXY_MAX_BODY_BYTES)) {
    throw new ProxyBodyTooLargeError();
  }
  if (!request.body) return undefined;
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > CHAMPION_PROXY_MAX_BODY_BYTES) {
      await reader.cancel();
      throw new ProxyBodyTooLargeError();
    }
    chunks.push(value);
  }
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
  return body;
}

class ProxyBodyTooLargeError extends Error {}

export async function proxyBackend(request: NextRequest, path: string) {
  try {
    const cookieToken = request.cookies.get("auth_token")?.value;
    const incomingAuthorization = request.headers.get("authorization");
    const headers = new Headers();
    if (cookieToken) headers.set("Authorization", `Bearer ${cookieToken}`);
    else if (incomingAuthorization?.startsWith("Bearer ")) headers.set("Authorization", incomingAuthorization);
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("Content-Type", contentType);
    const method = request.method;
    const body = method === "GET" || method === "HEAD" ? undefined : await readBoundedBody(request);
    const response = await fetch(`${BACKEND_URL}${path}`, {
      method,
      headers,
      body,
      cache: "no-store",
    });
    const responseType = response.headers.get("content-type") || "";
    // Preserve the backend status and bytes even for non-JSON or malformed
    // error bodies. Do not forward Set-Cookie or unrelated response headers.
    return new NextResponse(await response.arrayBuffer(), {
      status: response.status,
      headers: {
        ...(responseType ? { "Content-Type": responseType } : {}),
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    if (error instanceof ProxyBodyTooLargeError) {
      return NextResponse.json({ detail: "リクエスト容量が上限を超えています。" }, { status: 413 });
    }
    console.error("[champion-proxy] backend request failed", error);
    return NextResponse.json(
      { detail: "バックエンドへ接続できませんでした。時間をおいて再試行してください。" },
      { status: 502 },
    );
  }
}
