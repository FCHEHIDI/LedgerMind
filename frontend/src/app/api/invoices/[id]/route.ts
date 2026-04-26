import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  process.env.DJANGO_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://api.localhost:8888";

/**
 * GET /api/invoices/[id]
 * Proxy authentifié → Django GET /api/v1/invoices/<uuid>/
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });
  }

  const upstream = await fetch(`${API_BASE}/api/v1/invoices/${id}/`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}

/**
 * PATCH /api/invoices/[id]
 * Proxy authentifié → Django PATCH /api/v1/invoices/<uuid>/
 */
export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Corps JSON invalide." }, { status: 400 });
  }

  const upstream = await fetch(`${API_BASE}/api/v1/invoices/${id}/`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
