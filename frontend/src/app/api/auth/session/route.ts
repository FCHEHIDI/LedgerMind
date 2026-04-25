import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

const COOKIE_OPTS = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
};

const ACCESS_TTL = 60 * 5;        // 5 minutes (Django SimpleJWT default)
const REFRESH_TTL = 60 * 60 * 24; // 24 hours

export async function POST(req: NextRequest) {
  let body: { access?: string; refresh?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { access, refresh } = body;
  if (!access || !refresh) {
    return NextResponse.json({ error: "Missing tokens" }, { status: 400 });
  }

  const cookieStore = await cookies();
  cookieStore.set("access_token", access, { ...COOKIE_OPTS, maxAge: ACCESS_TTL });
  cookieStore.set("refresh_token", refresh, { ...COOKIE_OPTS, maxAge: REFRESH_TTL });

  return NextResponse.json({ ok: true });
}

export async function DELETE() {
  const cookieStore = await cookies();
  cookieStore.delete("access_token");
  cookieStore.delete("refresh_token");
  return NextResponse.json({ ok: true });
}
