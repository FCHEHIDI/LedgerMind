/**
 * Next.js proxy route — GET /api/journal/export/fec
 *
 * Forwards the request to Django with the access_token cookie injected.
 * Returns the FEC file as a streamed attachment so the browser triggers
 * a native file download.
 *
 * Query params forwarded as-is: from, to
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

  // Forward query string (from, to)
  const { searchParams } = req.nextUrl;
  const qs = searchParams.toString();
  const upstream = `${DJANGO_URL}/api/v1/journal/export/fec/${qs ? `?${qs}` : ""}`;

  const djangoRes = await fetch(upstream, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  if (!djangoRes.ok) {
    const body = await djangoRes.json().catch(() => ({}));
    return NextResponse.json(body, { status: djangoRes.status });
  }

  const content = await djangoRes.arrayBuffer();
  const disposition = djangoRes.headers.get("Content-Disposition") ?? 'attachment; filename="export_fec.txt"';

  return new NextResponse(content, {
    status: 200,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Content-Disposition": disposition,
    },
  });
}
