import type { NextConfig } from "next";

const DJANGO_URL =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

const nextConfig: NextConfig = {
  // Empêche Next.js de rediriger /foo/ → /foo (les API Django nécessitent le trailing slash)
  skipTrailingSlashRedirect: true,
  // Produit un output autonome (node server.js) pour les images Docker de production
  output: "standalone",
  async rewrites() {
    return [
      {
        // Avec trailing slash (Django l'exige par défaut)
        source: "/api/django/:path*/",
        destination: `${DJANGO_URL}/api/:path*/`,
      },
      {
        // Sans trailing slash — on l'ajoute dans la destination
        source: "/api/django/:path*",
        destination: `${DJANGO_URL}/api/:path*/`,
      },
    ];
  },
};

export default nextConfig;
