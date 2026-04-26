/**
 * Next.js proxy — GET /api/lettrage (list) and POST /api/lettrage (create)
 */
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

async function withToken(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) return { token: null, response: NextResponse.json({ error: "NOT_AUTHENTICATED" }, { status: 401 }) };
  return { token, response: null };
}

export async function GET(req: NextRequest): Promise<NextResponse> {
  const { token, response } = await withToken(req);
  if (!token) return response!;
  const qs = req.nextUrl.searchParams.toString();
  const djangoRes = await fetch(`${DJANGO_URL}/api/v1/lettrage/${qs ? `?${qs}` : ""}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  const data = await djangoRes.json();
  return NextResponse.json(data, { status: djangoRes.status });
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  const { token, response } = await withToken(req);
  if (!token) return response!;
  const body = await req.json().catch(() => ({}));
  const djangoRes = await fetch(`${DJANGO_URL}/api/v1/lettrage/`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await djangoRes.json();
  return NextResponse.json(data, { status: djangoRes.status });
}
