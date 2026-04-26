/**
 * Next.js proxy — GET /api/lettrage/open-items
 * Forwards to Django GET /api/v1/lettrage/open-items/
 * Query params: account_code, from, to
 */
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

export async function GET(req: NextRequest): Promise<NextResponse> {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) return NextResponse.json({ error: "NOT_AUTHENTICATED" }, { status: 401 });

  const qs = req.nextUrl.searchParams.toString();
  const djangoRes = await fetch(
    `${DJANGO_URL}/api/v1/lettrage/open-items/${qs ? `?${qs}` : ""}`,
    { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }
  );
  const data = await djangoRes.json();
  return NextResponse.json(data, { status: djangoRes.status });
}
