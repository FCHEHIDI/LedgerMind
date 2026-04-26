import { NextResponse } from "next/server";
import { cookies } from "next/headers";

const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://api.localhost:8888";

// POST /api/chart/seed-pcg — peuple le plan PCG standard
export async function POST() {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "Non authentifié" }, { status: 401 });

  const res = await fetch(`${DJANGO_URL}/api/v1/chart/seed-pcg/`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
