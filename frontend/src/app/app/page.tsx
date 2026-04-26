"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Org {
  id: string;
  name: string;
  siren: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

// ── Role labels ───────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<string, { label: string; style: string }> = {
  org_owner: {
    label: "Propriétaire",
    style: "bg-violet-100 text-violet-700 dark:bg-violet-950/40 dark:text-violet-400",
  },
  org_admin: {
    label: "Admin",
    style: "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400",
  },
  accountant: {
    label: "Comptable",
    style: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400",
  },
  auditor: {
    label: "Auditeur",
    style: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
  },
  ledgermind_staff: {
    label: "Staff",
    style: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  },
};

// ── Initials avatar ───────────────────────────────────────────────────────────

function OrgAvatar({ name }: { name: string }) {
  const initials = name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  // Deterministic color from name
  const colors = [
    "bg-blue-500",
    "bg-violet-500",
    "bg-emerald-500",
    "bg-amber-500",
    "bg-rose-500",
    "bg-cyan-500",
    "bg-indigo-500",
    "bg-teal-500",
  ];
  const idx = name.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0) % colors.length;

  return (
    <div
      className={`flex h-12 w-12 items-center justify-center rounded-xl text-white font-bold text-lg ${colors[idx]}`}
    >
      {initials || "?"}
    </div>
  );
}

// ── Org card ──────────────────────────────────────────────────────────────────

function OrgCard({
  org,
  onSelect,
  selecting,
}: {
  org: Org;
  onSelect: (org: Org) => void;
  selecting: string | null;
}) {
  const roleInfo = ROLE_LABELS[org.role] ?? { label: org.role, style: "bg-zinc-100 text-zinc-600" };
  const isSelecting = selecting === org.id;

  return (
    <button
      onClick={() => onSelect(org)}
      disabled={selecting !== null}
      className="group relative flex flex-col gap-4 rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 text-left shadow-sm hover:shadow-md hover:border-zinc-300 dark:hover:border-zinc-700 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <OrgAvatar name={org.name} />
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${roleInfo.style}`}
        >
          {roleInfo.label}
        </span>
      </div>

      {/* Name & SIREN */}
      <div>
        <h3 className="font-semibold text-zinc-900 dark:text-zinc-50 group-hover:text-zinc-700 dark:group-hover:text-zinc-200 transition-colors leading-snug">
          {org.name}
        </h3>
        <p className="mt-1 font-mono text-xs text-zinc-400 dark:text-zinc-500 tracking-wide">
          SIREN {org.siren}
        </p>
      </div>

      {/* CTA */}
      <div className="flex items-center justify-between mt-auto pt-2 border-t border-zinc-100 dark:border-zinc-800">
        <span className="text-xs text-zinc-400 dark:text-zinc-500">
          Accéder à la comptabilité
        </span>
        {isSelecting ? (
          <svg className="h-4 w-4 animate-spin text-zinc-400" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        ) : (
          <span className="text-sm text-zinc-400 group-hover:text-zinc-700 dark:group-hover:text-zinc-200 transition-colors">
            →
          </span>
        )}
      </div>
    </button>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AppHomePage() {
  const router = useRouter();
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selecting, setSelecting] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/organizations")
      .then((r) => r.json())
      .then((data: { results?: Org[] } | Org[]) => {
        const list = Array.isArray(data) ? data : (data.results ?? []);
        setOrgs(list);
        // Si une seule org → sélection automatique silencieuse
        if (list.length === 1) {
          void selectOrg(list[0], true);
        }
      })
      .catch(() => setError("Impossible de charger les organisations."))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function selectOrg(org: Org, silent = false) {
    if (!silent) setSelecting(org.id);
    try {
      await fetch("/api/org/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ orgId: org.id }),
      });
      router.push("/app/dashboard");
    } catch {
      setSelecting(null);
    }
  }

  // Skeleton
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full py-16">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 w-full max-w-3xl">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-48 rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-12">
      {/* Header */}
      <div className="mb-10 text-center">
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50 tracking-tight">
          LedgerMind
        </h1>
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          Sélectionnez un dossier client pour accéder à sa comptabilité
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/20 px-4 py-3 text-sm text-red-600 dark:text-red-400 max-w-md text-center">
          {error}
        </div>
      )}

      {/* Org grid */}
      {orgs.length === 0 && !error ? (
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="rounded-full bg-zinc-100 dark:bg-zinc-800 p-5 text-3xl">🏢</div>
          <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Aucune organisation trouvée
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-xs">
            Votre compte n&apos;est rattaché à aucune organisation. Contactez votre administrateur.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 w-full max-w-3xl">
          {orgs.map((org) => (
            <OrgCard
              key={org.id}
              org={org}
              onSelect={(o) => void selectOrg(o)}
              selecting={selecting}
            />
          ))}
        </div>
      )}

      {/* Footer */}
      <p className="mt-12 text-xs text-zinc-400 dark:text-zinc-600">
        {orgs.length > 0 && `${orgs.length} dossier${orgs.length > 1 ? "s" : ""} accessible${orgs.length > 1 ? "s" : ""}`}
      </p>
    </div>
  );
}
