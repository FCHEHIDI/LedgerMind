import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { buildProxyHeaders } from "@/lib/proxy";

const DJANGO = process.env.DJANGO_INTERNAL_URL ?? "http://django:8000";

// GET /api/org-requests → Django GET /api/v1/org-requests/
export async function GET() {
  const cookieStore = await cookies();
  const headers = buildProxyHeaders(cookieStore);
  if (!headers) return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });

  const res = await fetch(`${DJANGO}/api/v1/org-requests/`, { headers });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

// POST /api/org-requests → Django POST /api/v1/org-requests/
export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const headers = buildProxyHeaders(cookieStore);
  if (!headers) return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });

  const body = await req.json();
  const res = await fetch(`${DJANGO}/api/v1/org-requests/`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
