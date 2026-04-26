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

interface OrgRequest {
  id: string;
  name: string;
  siren: string;
  status: "pending" | "approved" | "rejected";
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

  const colors = [
    "bg-blue-500", "bg-violet-500", "bg-emerald-500", "bg-amber-500",
    "bg-rose-500", "bg-cyan-500", "bg-indigo-500", "bg-teal-500",
  ];
  const idx = name.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0) % colors.length;

  return (
    <div className={`flex h-12 w-12 items-center justify-center rounded-xl text-white font-bold text-lg ${colors[idx]}`}>
      {initials || "?"}
    </div>
  );
}

// ── Org card ──────────────────────────────────────────────────────────────────

function OrgCard({ org, onSelect, selecting }: {
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
      <div className="flex items-start justify-between gap-3">
        <OrgAvatar name={org.name} />
        <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${roleInfo.style}`}>
          {roleInfo.label}
        </span>
      </div>
      <div>
        <h3 className="font-semibold text-zinc-900 dark:text-zinc-50 group-hover:text-zinc-700 dark:group-hover:text-zinc-200 transition-colors leading-snug">
          {org.name}
        </h3>
        <p className="mt-1 font-mono text-xs text-zinc-400 dark:text-zinc-500 tracking-wide">
          SIREN {org.siren}
        </p>
      </div>
      <div className="flex items-center justify-between mt-auto pt-2 border-t border-zinc-100 dark:border-zinc-800">
        <span className="text-xs text-zinc-400 dark:text-zinc-500">Accéder à la comptabilité</span>
        {isSelecting ? (
          <svg className="h-4 w-4 animate-spin text-zinc-400" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        ) : (
          <span className="text-sm text-zinc-400 group-hover:text-zinc-700 dark:group-hover:text-zinc-200 transition-colors">→</span>
        )}
      </div>
    </button>
  );
}

// ── Request modal ─────────────────────────────────────────────────────────────

function RequestOrgModal({ onClose, onSuccess }: {
  onClose: () => void;
  onSuccess: (req: OrgRequest) => void;
}) {
  const [name, setName] = useState("");
  const [siren, setSiren] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/org-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), siren: siren.trim(), message: message.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        const msg = data?.siren?.[0] ?? data?.name?.[0] ?? data?.detail ?? "Erreur lors de la soumission.";
        setError(msg);
        return;
      }
      onSuccess(data as OrgRequest);
    } catch {
      setError("Impossible de joindre le serveur.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-8 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
            Demander un nouveau dossier
          </h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors text-xl leading-none">
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">
              Nom de l&apos;entreprise <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-50 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              placeholder="Acme SAS"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">
              SIREN <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={siren}
              onChange={(e) => setSiren(e.target.value.replace(/\D/g, "").slice(0, 9))}
              required
              maxLength={9}
              pattern="\d{9}"
              className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm font-mono text-zinc-900 dark:text-zinc-50 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              placeholder="123456789"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">
              Message (optionnel)
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-50 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 resize-none"
              placeholder="Contexte, urgence, informations complémentaires…"
            />
          </div>

          {error && (
            <p className="text-xs text-red-500 dark:text-red-400">{error}</p>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={submitting || siren.length !== 9 || !name.trim()}
              className="px-5 py-2 rounded-lg bg-zinc-900 dark:bg-zinc-50 text-white dark:text-zinc-900 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "Envoi…" : "Envoyer la demande"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AppHomePage() {
  const router = useRouter();
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selecting, setSelecting] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [myRequests, setMyRequests] = useState<OrgRequest[]>([]);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/organizations")
      .then((r) => r.json())
      .then((data: { results?: Org[] } | Org[]) => {
        const list = Array.isArray(data) ? data : (data.results ?? []);
        setOrgs(list);
        if (list.length === 1) {
          void selectOrg(list[0], true);
        }
      })
      .catch(() => setError("Impossible de charger les organisations."))
      .finally(() => setLoading(false));

    // Load own requests
    fetch("/api/org-requests")
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (!data) return;
        const list: OrgRequest[] = Array.isArray(data) ? data : (data.results ?? []);
        setMyRequests(list.filter((r) => r.status === "pending"));
      })
      .catch(() => {/* best-effort */});
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

  function handleRequestSuccess(req: OrgRequest) {
    setShowModal(false);
    setMyRequests((prev) => [req, ...prev]);
    setSuccessMsg(`Demande pour "${req.name}" soumise — en attente de validation.`);
    setTimeout(() => setSuccessMsg(null), 6000);
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full py-16">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 w-full max-w-3xl">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-48 rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <>
      {showModal && (
        <RequestOrgModal
          onClose={() => setShowModal(false)}
          onSuccess={handleRequestSuccess}
        />
      )}

      <div className="flex flex-col items-center justify-center py-12">
        {/* Header */}
        <div className="mb-10 w-full max-w-3xl flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50 tracking-tight">
              LedgerMind
            </h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Sélectionnez un dossier client pour accéder à sa comptabilité
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex-shrink-0 flex items-center gap-2 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors shadow-sm"
          >
            <span className="text-base leading-none">+</span>
            Nouveau dossier
            {myRequests.length > 0 && (
              <span className="ml-1 inline-flex items-center justify-center rounded-full bg-amber-500 text-white text-xs font-bold h-4 min-w-[1rem] px-1">
                {myRequests.length}
              </span>
            )}
          </button>
        </div>

        {/* Success banner */}
        {successMsg && (
          <div className="mb-6 w-full max-w-3xl rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/20 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-400">
            {successMsg}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mb-6 rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/20 px-4 py-3 text-sm text-red-600 dark:text-red-400 max-w-md text-center">
            {error}
          </div>
        )}

        {/* Pending requests banner */}
        {myRequests.length > 0 && (
          <div className="mb-6 w-full max-w-3xl rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/20 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
            <span className="font-medium">{myRequests.length} demande{myRequests.length > 1 ? "s" : ""} en attente</span>
            {" — "}
            {myRequests.map((r) => r.name).join(", ")}
          </div>
        )}

        {/* Org grid */}
        {orgs.length === 0 && !error ? (
          <div className="flex flex-col items-center gap-3 text-center">
            <div className="rounded-full bg-zinc-100 dark:bg-zinc-800 p-5 text-3xl">🏢</div>
            <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Aucune organisation trouvée</p>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-xs">
              Votre compte n&apos;est rattaché à aucune organisation.
              Cliquez sur <strong>+ Nouveau dossier</strong> pour faire une demande.
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
    </>
  );
}
