import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  process.env.DJANGO_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://api.localhost:8888";

/**
 * Proxy multipart upload → Django POST /api/v1/documents/upload/
 *
 * Forwards the raw multipart body so Django can parse it with
 * MultiPartParser. The access_token JWT cookie is injected as Bearer header.
 *
 * Returns:
 *   202: { invoice_id, job_id, status: "queued", message }
 *   400: validation errors from Django
 *   401: not authenticated
 */
export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;

  if (!token) {
    return NextResponse.json({ error: "Non authentifié" }, { status: 401 });
  }

  // Forward raw multipart body — do NOT convert to JSON
  const formData = await req.formData();

  const res = await fetch(`${API_BASE}/api/v1/documents/upload/`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      // Let fetch set the correct Content-Type with boundary automatically
    },
    body: formData,
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
