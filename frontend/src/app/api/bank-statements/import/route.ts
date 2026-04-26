/**
 * Next.js proxy — POST /api/bank-statements/import
 * Streams multipart CSV upload to Django.
 */
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

export async function POST(req: NextRequest): Promise<NextResponse> {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) return NextResponse.json({ error: "NOT_AUTHENTICATED" }, { status: 401 });

  // Forward the multipart body as-is
  const formData = await req.formData();
  const djangoRes = await fetch(`${DJANGO_URL}/api/v1/bank-statements/import/`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    // Note: do NOT set Content-Type; fetch sets multipart boundary automatically
    body: formData,
  });
  const data = await djangoRes.json();
  return NextResponse.json(data, { status: djangoRes.status });
}
