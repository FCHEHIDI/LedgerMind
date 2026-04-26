import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const API_BASE =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

/**
 * GET /api/organizations
 * Retourne la liste des organisations dont l'utilisateur est membre,
 * avec son rôle dans chacune (id, name, siren, role, is_active).
 */
export async function GET() {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });
  }

  const upstream = await fetch(`${API_BASE}/api/v1/organizations/`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
