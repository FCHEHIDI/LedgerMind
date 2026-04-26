/**
 * Next.js proxy — GET /api/reports/bilan
 *
 * Forwards to Django GET /api/v1/reports/bilan/
 * Supports ?at=YYYY-MM-DD[&exercice_from=YYYY-MM-DD][&format=csv]
 */
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

export async function GET(req: NextRequest): Promise<NextResponse> {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;

  if (!token) {
    return NextResponse.json({ error: "NOT_AUTHENTICATED" }, { status: 401 });
  }

  const qs = req.nextUrl.searchParams.toString();
  const upstream = `${DJANGO_URL}/api/v1/reports/bilan/${qs ? `?${qs}` : ""}`;

  const djangoRes = await fetch(upstream, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  const isCsv = req.nextUrl.searchParams.get("format") === "csv";

  if (!djangoRes.ok) {
    const body = await djangoRes.json().catch(() => ({}));
    return NextResponse.json(body, { status: djangoRes.status });
  }

  if (isCsv) {
    const content = await djangoRes.arrayBuffer();
    const disposition =
      djangoRes.headers.get("Content-Disposition") ?? 'attachment; filename="bilan.csv"';
    return new NextResponse(content, {
      status: 200,
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": disposition,
      },
    });
  }

  const data = await djangoRes.json();
  return NextResponse.json(data, { status: djangoRes.status });
}
