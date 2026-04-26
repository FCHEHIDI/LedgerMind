import { NextRequest, NextResponse } from "next/server";

const COOKIE_OPTS = {
  httpOnly: false, // lisible par JS client pour l'OrgContext
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
  maxAge: 60 * 60 * 24 * 30, // 30 jours
};

/**
 * POST /api/org/switch
 * Body: { orgId: string }
 * Stocke l'org active dans le cookie `active_org_id`.
 * Ce cookie est lu par tous les proxy routes pour envoyer X-Organization-Id à Django.
 */
export async function POST(req: NextRequest) {
  let body: { orgId?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { orgId } = body;
  if (!orgId || typeof orgId !== "string") {
    return NextResponse.json({ error: "orgId manquant" }, { status: 400 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set("active_org_id", orgId, COOKIE_OPTS);
  return response;
}

/**
 * DELETE /api/org/switch
 * Efface le cookie `active_org_id` (retour au mode auto = premier membership).
 */
export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete("active_org_id");
  return response;
}
