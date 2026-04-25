/**
 * Next.js proxy route — POST /api/journal/[id]/reverse
 *
 * Forwards to Django POST /api/v1/journal/{id}/reverse/
 * Returns the newly created reversal JournalEntry (draft).
 */
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  const { id } = await params;
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;

  if (!token) {
    return NextResponse.json({ error: "NOT_AUTHENTICATED" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));

  const djangoRes = await fetch(`${DJANGO_URL}/api/v1/journal/${id}/reverse/`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  const data = await djangoRes.json().catch(() => ({}));
  return NextResponse.json(data, { status: djangoRes.status });
}
