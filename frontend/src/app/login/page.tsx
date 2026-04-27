"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";

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
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: "var(--bg-root)" }}
    >
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="inline-flex items-center gap-2.5 mb-3">
            <div
              style={{ background: "var(--amber-500)", borderRadius: "10px" }}
              className="flex h-9 w-9 items-center justify-center"
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M4 5h10M4 9h7M4 13h5" stroke="#131110" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </div>
            <span className="text-xl font-semibold tracking-tight" style={{ color: "var(--text-primary)" }}>
              <span style={{ color: "var(--amber-600)" }}>Ledger</span>Mind
            </span>
          </div>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Connectez-vous à votre espace
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          noValidate
          className="rounded-2xl p-8 space-y-5"
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-md)",
          }}
        >
          {error && (
            <p
              role="alert"
              className="rounded-lg px-4 py-3 text-sm"
              style={{
                background: "var(--danger-bg)",
                border: "1px solid var(--danger-border)",
                color: "var(--danger)",
              }}
            >
              {error}
            </p>
          )}

          <div className="space-y-1.5">
            <label
              htmlFor="email"
              className="block text-sm font-medium"
              style={{ color: "var(--text-primary)" }}
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
              placeholder="vous@example.com"
              className="w-full rounded-lg px-3 py-2 text-sm outline-none transition-all"
              style={{
                background: "var(--bg-root)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
              onFocus={(e) => {
                e.target.style.border = "1px solid var(--amber-400)";
                e.target.style.boxShadow = "0 0 0 3px rgba(245,158,11,0.12)";
              }}
              onBlur={(e) => {
                e.target.style.border = "1px solid var(--border)";
                e.target.style.boxShadow = "none";
              }}
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="password"
              className="block text-sm font-medium"
              style={{ color: "var(--text-primary)" }}
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
                placeholder="••••••••"
                className="w-full rounded-lg px-3 py-2 pr-10 text-sm outline-none transition-all"
                style={{
                  background: "var(--bg-root)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                }}
                onFocus={(e) => {
                  e.target.style.border = "1px solid var(--amber-400)";
                  e.target.style.boxShadow = "0 0 0 3px rgba(245,158,11,0.12)";
                }}
                onBlur={(e) => {
                  e.target.style.border = "1px solid var(--border)";
                  e.target.style.boxShadow = "none";
                }}
              />
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                className="absolute right-2.5 transition-colors"
                style={{ color: "var(--text-tertiary)" }}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg px-4 py-2.5 text-sm font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: "var(--amber-600)",
              color: "#fff",
              boxShadow: "var(--shadow-amber)",
            }}
            onMouseEnter={(e) => {
              if (!loading) e.currentTarget.style.background = "var(--amber-700)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "var(--amber-600)";
            }}
          >
            {loading ? "Connexion…" : "Se connecter"}
          </button>
        </form>

        <p className="mt-6 text-center text-xs" style={{ color: "var(--text-tertiary)" }}>
          LedgerMind — Plateforme de comptabilité intelligente
        </p>
      </div>
    </div>
  );
}

