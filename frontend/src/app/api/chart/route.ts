import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://api.localhost:8888";

// GET /api/chart?class=&type=&active=&search=
// POST /api/chart  { account_code, account_label, ... }
export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "Non authentifié" }, { status: 401 });

  const params = req.nextUrl.searchParams.toString();
  const url = `${DJANGO_URL}/api/v1/chart/${params ? `?${params}` : ""}`;

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "Non authentifié" }, { status: 401 });

  const body = await req.json();
  const res = await fetch(`${DJANGO_URL}/api/v1/chart/`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
