import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/api/"];

// URL interne Django (réseau Docker ou loopback en dev local)
const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

const COOKIE_OPTS = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
  maxAge: 60 * 5, // 5 minutes — aligné sur SimpleJWT ACCESS_TOKEN_LIFETIME
};

/**
 * Détecte les requêtes internes de Next.js (RSC prefetch, HMR, etc.)
 * Pour ces requêtes on ne fait PAS de redirect (ça casserait le router client),
 * on se contente d'injecter le cookie ou de passer.
 */
function isInternalNextRequest(req: NextRequest): boolean {
  // RSC payload requests (App Router navigation côté client)
  if (req.nextUrl.searchParams.has("_rsc")) return true;
  // Prefetch requests
  if (req.headers.get("Next-Router-Prefetch") === "1") return true;
  // RSC Accept header
  const accept = req.headers.get("Accept") ?? "";
  if (accept.includes("text/x-component")) return true;
  return false;
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Laisser passer les routes publiques et les assets statiques
  const isPublic =
    PUBLIC_PATHS.some((p) => pathname.startsWith(p)) ||
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/favicon") ||
    /\.(png|jpg|jpeg|gif|svg|ico|webp|woff2?|ttf|otf)$/.test(pathname);

  if (isPublic) return NextResponse.next();

  // Token valide présent — laisser passer
  const accessToken = req.cookies.get("access_token");
  if (accessToken) return NextResponse.next();

  // Pas d'access_token — tenter un refresh silencieux
  const refreshToken = req.cookies.get("refresh_token");
  if (!refreshToken) {
    // Aucun token disponible → login (sauf requêtes internes Next.js)
    if (isInternalNextRequest(req)) return NextResponse.next();
    return NextResponse.redirect(new URL("/login", req.url));
  }

  try {
    const refreshRes = await fetch(`${DJANGO_URL}/api/v1/auth/token/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: refreshToken.value }),
    });

    if (!refreshRes.ok) {
      // Refresh token invalide ou expiré → effacer et rediriger vers login
      if (isInternalNextRequest(req)) return NextResponse.next();
      const loginResp = NextResponse.redirect(new URL("/login", req.url));
      loginResp.cookies.delete("access_token");
      loginResp.cookies.delete("refresh_token");
      return loginResp;
    }

    const { access } = await refreshRes.json();

    // Requêtes internes Next.js (RSC prefetch, etc.) : on injecte juste le cookie
    // sans faire de redirect (le redirect casserait le router client)
    if (isInternalNextRequest(req)) {
      const response = NextResponse.next();
      response.cookies.set("access_token", access, COOKIE_OPTS);
      return response;
    }

    // Requête navigation normale : rediriger vers la même URL avec le nouveau cookie.
    // Le second round-trip aura le cookie frais, ce qui permet aux Server
    // Components de lire access_token directement depuis la requête.
    const response = NextResponse.redirect(req.url);
    response.cookies.set("access_token", access, COOKIE_OPTS);
    return response;
  } catch {
    // Django injoignable (démarrage, réseau) — ne pas déconnecter l'utilisateur
    return NextResponse.next();
  }
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
