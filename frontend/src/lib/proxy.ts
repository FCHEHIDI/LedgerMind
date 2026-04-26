import { ReadonlyRequestCookies } from "next/dist/server/web/spec-extension/adapters/request-cookies";

/**
 * buildProxyHeaders — construit les headers Authorization + X-Organization-Id
 * à partir du cookie store serveur (Next.js route handlers).
 *
 * Usage dans un route handler :
 *   const cookieStore = await cookies();
 *   const headers = buildProxyHeaders(cookieStore);
 *   if (!headers) return NextResponse.json({ detail: "Non authentifié." }, { status: 401 });
 *
 * @param cookieStore - Résultat de `await cookies()` dans un route handler Next.js
 * @returns Headers object prêt pour fetch() vers Django, ou null si non authentifié
 */
export function buildProxyHeaders(
  cookieStore: ReadonlyRequestCookies
): Record<string, string> | null {
  const token = cookieStore.get("access_token")?.value;
  if (!token) return null;

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  const activeOrg = cookieStore.get("active_org_id")?.value;
  if (activeOrg) {
    headers["X-Organization-Id"] = activeOrg;
  }

  return headers;
}
