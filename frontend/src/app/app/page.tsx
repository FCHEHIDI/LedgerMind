"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Plus, ArrowRight, Loader2, Building2, Clock } from "lucide-react";

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

// ── Role config ───────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<string, { label: string; color: string; bg: string; border: string }> = {
  org_owner: {
    label: "Propriétaire",
    color: "#7C3AED",
    bg: "#F5F3FF",
    border: "#DDD6FE",
  },
  org_admin: {
    label: "Admin",
    color: "#2563EB",
    bg: "#EFF6FF",
    border: "#BFDBFE",
  },
  accountant: {
    label: "Comptable",
    color: "#059669",
    bg: "#ECFDF5",
    border: "#A7F3D0",
  },
  auditor: {
    label: "Auditeur",
    color: "#D97706",
    bg: "#FFFBEB",
    border: "#FDE68A",
  },
  ledgermind_staff: {
    label: "Staff",
    color: "#6B6460",
    bg: "#F7F5F2",
    border: "#E8E3DC",
  },
};

// ── Initials avatar ───────────────────────────────────────────────────────────

const AVATAR_COLORS = [
  "#7C3AED", "#2563EB", "#059669", "#F59E0B",
  "#DC2626", "#0891B2", "#4F46E5", "#0D9488",
];

function OrgAvatar({ name, size = 48 }: { name: string; size?: number }) {
  const initials = name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  const color = AVATAR_COLORS[
    name.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0) % AVATAR_COLORS.length
  ];
  return (
    <div
      className="flex items-center justify-center rounded-xl font-bold text-white"
      style={{ width: size, height: size, background: color, fontSize: size * 0.35 }}
    >
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
  const roleInfo = ROLE_LABELS[org.role] ?? ROLE_LABELS.ledgermind_staff;
  const isSelecting = selecting === org.id;
  const isDisabled = selecting !== null;

  return (
    <button
      onClick={() => onSelect(org)}
      disabled={isDisabled}
      className="group relative flex flex-col gap-4 rounded-2xl text-left transition-all disabled:opacity-60 disabled:cursor-not-allowed"
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        boxShadow: "var(--shadow-sm)",
        padding: "24px",
      }}
      onMouseEnter={(e) => {
        if (!isDisabled) {
          e.currentTarget.style.boxShadow = "var(--shadow-md)";
          e.currentTarget.style.borderColor = "var(--amber-300)";
        }
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = "var(--shadow-sm)";
        e.currentTarget.style.borderColor = "var(--border)";
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <OrgAvatar name={org.name} />
        <span
          className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium"
          style={{
            color: roleInfo.color,
            background: roleInfo.bg,
            border: `1px solid ${roleInfo.border}`,
          }}
        >
          {roleInfo.label}
        </span>
      </div>

      <div>
        <h3 className="font-semibold leading-snug" style={{ color: "var(--text-primary)" }}>
          {org.name}
        </h3>
        <p className="mt-1 font-mono text-xs tracking-wide" style={{ color: "var(--text-tertiary)" }}>
          SIREN {org.siren}
        </p>
      </div>

      <div
        className="flex items-center justify-between mt-auto pt-3"
        style={{ borderTop: "1px solid var(--border-light)" }}
      >
        <span className="text-xs" style={{ color: "var(--text-tertiary)" }}>
          Accéder à la comptabilité
        </span>
        {isSelecting ? (
          <Loader2 size={14} className="animate-spin" style={{ color: "var(--amber-500)" }} />
        ) : (
          <ArrowRight
            size={14}
            style={{ color: "var(--text-tertiary)" }}
            className="transition-transform group-hover:translate-x-0.5"
          />
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
        setError(data?.siren?.[0] ?? data?.name?.[0] ?? data?.detail ?? "Erreur lors de la soumission.");
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
      <div
        className="w-full max-w-md rounded-2xl p-8"
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-md)",
        }}
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            Nouveau dossier
          </h2>
          <button
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-lg leading-none transition-colors"
            style={{ color: "var(--text-tertiary)" }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-root)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {[
            { id: "org-name", label: "Nom de l'entreprise", required: true, value: name, onChange: setName, placeholder: "Acme SAS", type: "text" },
          ].map(({ id, label, required, value, onChange, placeholder, type }) => (
            <div key={id}>
              <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-secondary)" }}>
                {label} {required && <span style={{ color: "var(--danger)" }}>*</span>}
              </label>
              <input
                id={id}
                type={type}
                value={value}
                onChange={(e) => onChange(e.target.value)}
                required={required}
                placeholder={placeholder}
                className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                style={{ background: "var(--bg-root)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                onFocus={(e) => { e.target.style.border = "1px solid var(--amber-400)"; e.target.style.boxShadow = "0 0 0 3px rgba(245,158,11,0.12)"; }}
                onBlur={(e) => { e.target.style.border = "1px solid var(--border)"; e.target.style.boxShadow = "none"; }}
              />
            </div>
          ))}

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-secondary)" }}>
              SIREN <span style={{ color: "var(--danger)" }}>*</span>
            </label>
            <input
              type="text"
              value={siren}
              onChange={(e) => setSiren(e.target.value.replace(/\D/g, "").slice(0, 9))}
              required
              maxLength={9}
              pattern="\d{9}"
              placeholder="123456789"
              className="w-full rounded-lg px-3 py-2 text-sm font-mono outline-none"
              style={{ background: "var(--bg-root)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              onFocus={(e) => { e.target.style.border = "1px solid var(--amber-400)"; e.target.style.boxShadow = "0 0 0 3px rgba(245,158,11,0.12)"; }}
              onBlur={(e) => { e.target.style.border = "1px solid var(--border)"; e.target.style.boxShadow = "none"; }}
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-secondary)" }}>
              Message (optionnel)
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              placeholder="Contexte, urgence, informations complémentaires…"
              className="w-full rounded-lg px-3 py-2 text-sm outline-none resize-none"
              style={{ background: "var(--bg-root)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              onFocus={(e) => { e.target.style.border = "1px solid var(--amber-400)"; e.target.style.boxShadow = "0 0 0 3px rgba(245,158,11,0.12)"; }}
              onBlur={(e) => { e.target.style.border = "1px solid var(--border)"; e.target.style.boxShadow = "none"; }}
            />
          </div>

          {error && (
            <p className="text-xs" style={{ color: "var(--danger)" }}>{error}</p>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm transition-colors"
              style={{ color: "var(--text-secondary)" }}
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={submitting || siren.length !== 9 || !name.trim()}
              className="px-5 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ background: "var(--amber-600)", color: "#fff", boxShadow: "var(--shadow-amber)" }}
              onMouseEnter={(e) => { if (!submitting) e.currentTarget.style.background = "var(--amber-700)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "var(--amber-600)"; }}
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

    fetch("/api/org-requests")
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (!data) return;
        const list: OrgRequest[] = Array.isArray(data) ? data : (data.results ?? []);
        setMyRequests(list.filter((r) => r.status === "pending"));
      })
      .catch(() => {});
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
      <div className="flex items-center justify-center h-64">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 w-full max-w-3xl">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-48 rounded-2xl animate-pulse"
              style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
            />
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

      <div className="flex flex-col items-center py-12">
        {/* Header */}
        <div className="mb-8 w-full max-w-3xl flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
              Sélectionner un dossier
            </h1>
            <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
              Accédez à la comptabilité d&apos;un dossier client
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex shrink-0 items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-all"
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
              boxShadow: "var(--shadow-xs)",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--amber-400)")}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
          >
            <Plus size={14} />
            Nouveau dossier
            {myRequests.length > 0 && (
              <span
                className="ml-1 inline-flex items-center justify-center rounded-full text-white text-xs font-bold h-4 min-w-4 px-1"
                style={{ background: "var(--amber-500)" }}
              >
                {myRequests.length}
              </span>
            )}
          </button>
        </div>

        {/* Success banner */}
        {successMsg && (
          <div
            className="mb-6 w-full max-w-3xl rounded-xl px-4 py-3 text-sm"
            style={{
              background: "var(--success-bg)",
              border: "1px solid var(--success-border)",
              color: "var(--success)",
            }}
          >
            {successMsg}
          </div>
        )}

        {/* Error */}
        {error && (
          <div
            className="mb-6 rounded-xl px-4 py-3 text-sm max-w-md text-center"
            style={{
              background: "var(--danger-bg)",
              border: "1px solid var(--danger-border)",
              color: "var(--danger)",
            }}
          >
            {error}
          </div>
        )}

        {/* Pending requests */}
        {myRequests.length > 0 && (
          <div
            className="mb-6 w-full max-w-3xl flex items-center gap-3 rounded-xl px-4 py-3 text-sm"
            style={{
              background: "var(--warning-bg)",
              border: "1px solid var(--warning-border)",
              color: "var(--warning)",
            }}
          >
            <Clock size={14} className="shrink-0" />
            <span>
              <span className="font-medium">{myRequests.length} demande{myRequests.length > 1 ? "s" : ""} en attente</span>
              {" — "}{myRequests.map((r) => r.name).join(", ")}
            </span>
          </div>
        )}

        {/* Org grid */}
        {orgs.length === 0 && !error ? (
          <div className="flex flex-col items-center gap-4 text-center py-12">
            <div
              className="flex h-16 w-16 items-center justify-center rounded-2xl"
              style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
            >
              <Building2 size={28} style={{ color: "var(--text-tertiary)" }} />
            </div>
            <div>
              <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                Aucune organisation trouvée
              </p>
              <p className="text-xs mt-1 max-w-xs" style={{ color: "var(--text-secondary)" }}>
                Votre compte n&apos;est rattaché à aucune organisation.
                Cliquez sur <strong>+ Nouveau dossier</strong> pour faire une demande.
              </p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 w-full max-w-3xl">
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
        {orgs.length > 0 && (
          <p className="mt-10 text-xs" style={{ color: "var(--text-tertiary)" }}>
            {orgs.length} dossier{orgs.length > 1 ? "s" : ""} accessible{orgs.length > 1 ? "s" : ""}
          </p>
        )}
      </div>
    </>
  );
}
