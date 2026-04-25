import type { NextConfig } from "next";

const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        // Proxy toutes les requêtes /api/django/* vers Django
        // Le navigateur ne voit que /api/django/* → pas de CORS
        source: "/api/django/:path*",
        destination: `${DJANGO_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
