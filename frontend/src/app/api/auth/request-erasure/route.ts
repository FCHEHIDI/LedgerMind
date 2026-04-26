import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { buildProxyHeaders } from "@/lib/proxy";

const DJANGO = process.env.DJANGO_INTERNAL_URL ?? "http://django:8000";

/**
 * POST /api/auth/request-erasure
 *
 * Crée une demande d'effacement RGPD (Art. 17) pour l'utilisateur connecté.
 * Proxifié vers Django POST /api/v1/auth/request-erasure/
 *
 * Réponses:
 *   201 — Demande créée { id, status, requested_at }
 *   400 — Une demande est déjà en cours
 *   401 — Non authentifié
 */
export async function POST() {
  const cookieStore = await cookies();
  const headers = buildProxyHeaders(cookieStore);
  if (!headers) {
    return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });
  }

  const res = await fetch(`${DJANGO}/api/v1/auth/request-erasure/`, {
    method: "POST",
    headers,
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
