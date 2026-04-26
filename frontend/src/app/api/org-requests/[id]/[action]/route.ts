import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { buildProxyHeaders } from "@/lib/proxy";

const DJANGO = process.env.DJANGO_INTERNAL_URL ?? "http://django:8000";

// POST /api/org-requests/[id]/approve → Django POST /api/v1/org-requests/<id>/approve/
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string; action: string }> }
) {
  const { id, action } = await params;

  if (action !== "approve" && action !== "reject") {
    return NextResponse.json({ detail: "Action invalide." }, { status: 400 });
  }

  const cookieStore = await cookies();
  const headers = buildProxyHeaders(cookieStore);
  if (!headers) return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const res = await fetch(`${DJANGO}/api/v1/org-requests/${id}/${action}/`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
