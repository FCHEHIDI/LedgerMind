import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  process.env.DJANGO_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://api.localhost:8888";

/**
 * GET /api/invoices?status=&search=&page=
 * Proxy authentifié → Django GET /api/v1/invoices/
 */
export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });
  }

  const { searchParams } = new URL(req.url);
  const upstream = await fetch(
    `${API_BASE}/api/v1/invoices/?${searchParams.toString()}`,
    {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    }
  );

  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}

/**
 * POST /api/invoices
 * Proxy authentifié → Django POST /api/v1/invoices/
 */
export async function POST(req: NextRequest) {
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

  const upstream = await fetch(`${API_BASE}/api/v1/invoices/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
