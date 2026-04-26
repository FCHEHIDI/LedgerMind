import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { buildProxyHeaders } from "@/lib/proxy";

const API_BASE =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

/**
 * GET /api/journal?page_size=&page=
 * Proxy authentifié vers Django GET /api/v1/journal/
 */
export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const headers = buildProxyHeaders(cookieStore);
  if (!headers) return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });

  const { searchParams } = new URL(req.url);
  const upstream = await fetch(
    `${API_BASE}/api/v1/journal/?${searchParams.toString()}`,
    { headers, cache: "no-store" }
  );

  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}

/**
 * POST /api/journal
 * Proxy authentifié vers Django POST /api/v1/journal/
 */
export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const headers = buildProxyHeaders(cookieStore);
  if (!headers) return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Corps JSON invalide." }, { status: 400 });
  }

  const upstream = await fetch(`${API_BASE}/api/v1/journal/`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
