/**
 * Next.js proxy — GET/DELETE /api/lettrage/[id]
 */
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

async function proxy(req: NextRequest, id: string): Promise<NextResponse> {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) return NextResponse.json({ error: "NOT_AUTHENTICATED" }, { status: 401 });

  const djangoRes = await fetch(`${DJANGO_URL}/api/v1/lettrage/${id}/`, {
    method: req.method,
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  if (djangoRes.status === 204) return new NextResponse(null, { status: 204 });
  const data = await djangoRes.json();
  return NextResponse.json(data, { status: djangoRes.status });
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  const { id } = await params;
  return proxy(req, id);
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
): Promise<NextResponse> {
  const { id } = await params;
  return proxy(req, id);
}
