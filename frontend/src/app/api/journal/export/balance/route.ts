/**
 * Next.js proxy — GET /api/journal/export/balance
 * Forwards to Django GET /api/v1/journal/export/balance/
 * Query params: from, to, account_prefix, format (json|csv)
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
    `${DJANGO_URL}/api/v1/journal/export/balance/${qs ? `?${qs}` : ""}`,
    { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }
  );

  if (req.nextUrl.searchParams.get("format") === "csv") {
    if (!djangoRes.ok) return NextResponse.json({}, { status: djangoRes.status });
    const content = await djangoRes.arrayBuffer();
    const disposition = djangoRes.headers.get("Content-Disposition") ?? 'attachment; filename="balance.csv"';
    return new NextResponse(content, {
      status: 200,
      headers: { "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": disposition },
    });
  }

  const data = await djangoRes.json();
  return NextResponse.json(data, { status: djangoRes.status });
}
