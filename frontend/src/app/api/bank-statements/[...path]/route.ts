/**
 * Next.js catch-all proxy — /api/bank-statements/[...path]
 *
 * Handles:
 *   GET    /api/bank-statements/{id}               → detail
 *   GET    /api/bank-statements/{id}/report        → reconciliation report
 *   POST   /api/bank-statements/{id}/auto-match    → auto matching
 *   POST   /api/bank-statements/{id}/match-line    → manual match
 *   POST   /api/bank-statements/{id}/unmatch-line  → unmatch
 *   POST   /api/bank-statements/{id}/ignore-line   → ignore
 *   DELETE /api/bank-statements/{id}               → delete statement
 */
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

async function proxy(
  req: NextRequest,
  segments: string[]
): Promise<NextResponse> {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) return NextResponse.json({ error: "NOT_AUTHENTICATED" }, { status: 401 });

  const djangoPath = `/api/v1/bank-statements/${segments.join("/")}/`;
  const qs = req.nextUrl.searchParams.toString();
  const upstream = `${DJANGO_URL}${djangoPath}${qs ? `?${qs}` : ""}`;

  const init: RequestInit = {
    method: req.method,
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  };

  if (req.method === "POST" || req.method === "PATCH" || req.method === "PUT") {
    const body = await req.json().catch(() => null);
    if (body !== null) {
      (init.headers as Record<string, string>)["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
  }

  const djangoRes = await fetch(upstream, init);

  if (djangoRes.status === 204) {
    return new NextResponse(null, { status: 204 });
  }

  const contentType = djangoRes.headers.get("Content-Type") ?? "";
  if (contentType.includes("application/json")) {
    const data = await djangoRes.json();
    return NextResponse.json(data, { status: djangoRes.status });
  }

  // Pass through other content types (CSV, etc.)
  const content = await djangoRes.arrayBuffer();
  return new NextResponse(content, {
    status: djangoRes.status,
    headers: {
      "Content-Type": contentType || "application/octet-stream",
      "Content-Disposition": djangoRes.headers.get("Content-Disposition") ?? "",
    },
  });
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  const { path } = await params;
  return proxy(req, path);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  const { path } = await params;
  return proxy(req, path);
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  const { path } = await params;
  return proxy(req, path);
}
