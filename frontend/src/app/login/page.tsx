"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

// Proxy via Next.js rewrites (/api/django/*) — évite le CORS en dev et prod
const DJANGO_PROXY = "/api/django";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch(`${DJANGO_PROXY}/v1/auth/token/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // SimpleJWT attend "username" + "password" (modèle User Django standard)
        body: JSON.stringify({ username: email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(
          data?.detail ?? data?.non_field_errors?.[0] ?? "Email ou mot de passe incorrect."
        );
        return;
      }

      const { access, refresh } = await res.json();
      // Stocker via la route API Next.js pour cookies HTTP-only
      await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access, refresh }),
      });

      router.push("/app");
    } catch {
      setError("Impossible de joindre le serveur. Vérifiez votre connexion.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-950 px-4">
      <div className="w-full max-w-sm">
        {/* Logo / titre */}
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
            LedgerMind
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Connectez-vous à votre espace
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          noValidate
          className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-8 shadow-sm space-y-5"
        >
          {error && (
            <p
              role="alert"
              className="rounded-lg bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-400"
            >
              {error}
            </p>
          )}

          <div className="space-y-1">
            <label
              htmlFor="email"
              className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-50 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:focus:ring-zinc-50 transition"
              placeholder="vous@example.com"
            />
          </div>

          <div className="space-y-1">
            <label
              htmlFor="password"
              className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
            >
              Mot de passe
            </label>
            <div className="relative flex items-center">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 pr-10 text-sm text-zinc-900 dark:text-zinc-50 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:focus:ring-zinc-50 transition"
                placeholder="••••••••"
              />
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                className="absolute right-2.5 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition"
              >
                {showPassword ? (
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-zinc-900 dark:bg-zinc-50 px-4 py-2.5 text-sm font-semibold text-white dark:text-zinc-900 hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {loading ? "Connexion…" : "Se connecter"}
          </button>
        </form>
      </div>
    </div>
  );
}
