import { cookies } from "next/headers";
import Link from "next/link";

const API_BASE =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────

interface DashboardMetrics {
  total_journal_entries: number;
  pending_entries: number;
  documents_count: number;
  compliance_alerts: number;
}

interface JournalEntry {
  id: string;
  reference: string | null;
  journal_code: string;
  entry_date: string;
  status: "draft" | "posted" | "cancelled";
  created_at: string;
}

interface JournalListResponse {
  count?: number;
  results?: JournalEntry[];
}

interface CompteDeResultat {
  produits: { total: string };
  charges: { total: string };
  resultat_net: string;
  resultat_type: "benefice" | "perte";
}

interface TvaCA3 {
  tva_collectee: { total: string };
  tva_deductible: { total: string };
  solde_net: string;
  resultat: "tva_a_payer" | "credit_tva" | "equilibre";
}

// ── Fetchers ─────────────────────────────────────────────────────────────────

async function getToken(): Promise<string | null> {
  const cookieStore = await cookies();
  return cookieStore.get("access_token")?.value ?? null;
}

async function fetchMetrics(token: string): Promise<DashboardMetrics | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/dashboard/metrics/`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function fetchRecentEntries(token: string): Promise<JournalEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/journal/?page_size=6`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return [];
    const data: JournalListResponse | JournalEntry[] = await res.json();
    if (Array.isArray(data)) return data.slice(0, 6);
    return data.results?.slice(0, 6) ?? [];
  } catch {
    return [];
  }
}

async function fetchResultat(token: string, year: number): Promise<CompteDeResultat | null> {
  try {
    const res = await fetch(
      `${API_BASE}/api/v1/reports/compte-de-resultat/?from=${year}-01-01&to=${year}-12-31`,
      { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function fetchTva(token: string, year: number): Promise<TvaCA3 | null> {
  try {
    const res = await fetch(
      `${API_BASE}/api/v1/tva/ca3/?from=${year}-01-01&to=${year}-12-31`,
      { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatAmount(value: string | null | undefined): string {
  if (!value) return "—";
  const num = parseFloat(value);
  if (isNaN(num)) return "—";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(num);
}

// ── UI Components ─────────────────────────────────────────────────────────────

type MetricAccent = "neutral" | "warning" | "danger" | "success" | "amber";

const ACCENT_COLORS: Record<MetricAccent, string> = {
  neutral: "#6B6460",
  warning: "#D97706",
  danger:  "#DC2626",
  success: "#059669",
  amber:   "#F59E0B",
};

function MetricCard({
  label,
  value,
  description,
  accent = "neutral",
}: {
  label: string;
  value: number | string;
  description?: string;
  accent?: MetricAccent;
}) {
  const color = ACCENT_COLORS[accent];
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* Colored top bar */}
      <div style={{ height: "3px", background: color }} />
      <div className="p-5">
        <p className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {label}
        </p>
        <p className="mt-2 text-3xl font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>
          {value}
        </p>
        {description && (
          <p className="mt-1 text-xs" style={{ color: "var(--text-tertiary)" }}>
            {description}
          </p>
        )}
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <div
      className="rounded-xl overflow-hidden animate-pulse"
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
    >
      <div style={{ height: "3px", background: "var(--border)" }} />
      <div className="p-5">
        <div className="h-3 w-28 rounded" style={{ background: "var(--border-light)" }} />
        <div className="mt-3 h-8 w-16 rounded" style={{ background: "var(--border-light)" }} />
      </div>
    </div>
  );
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  draft: {
    label: "Brouillon",
    color: "var(--warning)",
    bg: "var(--warning-bg)",
    border: "var(--warning-border)",
  },
  posted: {
    label: "Validée",
    color: "var(--success)",
    bg: "var(--success-bg)",
    border: "var(--success-border)",
  },
  cancelled: {
    label: "Annulée",
    color: "var(--danger)",
    bg: "var(--danger-bg)",
    border: "var(--danger-border)",
  },
};

const JOURNAL_LABELS: Record<string, string> = {
  ACH: "Achats",
  VTE: "Ventes",
  BQ:  "Banque",
  OD:  "OD",
  AN:  "À-nouveaux",
  PAI: "Paiements",
};

const JOURNAL_COLORS: Record<string, string> = {
  ACH: "#7C3AED",
  VTE: "#2563EB",
  BQ:  "#059669",
  OD:  "#D97706",
  AN:  "#6B7280",
  PAI: "#0891B2",
};

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function DashboardPage() {
  const token = await getToken();
  const year = new Date().getFullYear();

  if (!token) {
    return (
      <div
        className="flex items-center justify-center h-64 text-sm"
        style={{ color: "var(--text-tertiary)" }}
      >
        Session expirée — veuillez vous reconnecter.
      </div>
    );
  }

  const [metricsResult, entriesResult, resultatResult, tvaResult] = await Promise.allSettled([
    fetchMetrics(token),
    fetchRecentEntries(token),
    fetchResultat(token, year),
    fetchTva(token, year),
  ]);

  const metrics = metricsResult.status === "fulfilled" ? metricsResult.value : null;
  const entries = entriesResult.status === "fulfilled" ? entriesResult.value : [];
  const resultat = resultatResult.status === "fulfilled" ? resultatResult.value : null;
  const tva = tvaResult.status === "fulfilled" ? tvaResult.value : null;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
          Tableau de bord
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Vue d&apos;ensemble de votre activité comptable — exercice {year}
        </p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {metrics ? (
          <>
            <MetricCard
              label="Écritures totales"
              value={metrics.total_journal_entries}
              description="Toutes périodes"
              accent="amber"
            />
            <MetricCard
              label="En attente"
              value={metrics.pending_entries}
              description="Écritures à valider"
              accent={metrics.pending_entries > 0 ? "warning" : "neutral"}
            />
            <MetricCard
              label="Documents"
              value={metrics.documents_count}
              description="Factures importées"
              accent="success"
            />
            <MetricCard
              label="Alertes conformité"
              value={metrics.compliance_alerts}
              description="À traiter"
              accent={metrics.compliance_alerts > 0 ? "danger" : "neutral"}
            />
          </>
        ) : (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        )}
      </div>

      {/* Main content: entries table + financial summary */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">

        {/* Recent entries table — 2/3 */}
        <div
          className="lg:col-span-2 rounded-xl overflow-hidden"
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div
            className="flex items-center justify-between px-6 py-4"
            style={{ borderBottom: "1px solid var(--border-light)" }}
          >
            <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Dernières écritures
            </h2>
            <Link
              href="/app/ledger"
              className="text-xs transition-colors"
              style={{ color: "var(--text-tertiary)" }}
            >
              Voir tout →
            </Link>
          </div>

          {entries.length === 0 ? (
            <div className="px-6 py-10 text-center text-sm" style={{ color: "var(--text-tertiary)" }}>
              Aucune écriture enregistrée pour le moment.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-light)" }}>
                    {["Référence", "Journal", "Date", "Statut"].map((h) => (
                      <th
                        key={h}
                        className="px-6 py-3 text-left text-[11px] font-semibold uppercase tracking-wide"
                        style={{ color: "var(--text-tertiary)" }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry, i) => {
                    const badge = STATUS_CONFIG[entry.status] ?? STATUS_CONFIG.draft;
                    const jColor = JOURNAL_COLORS[entry.journal_code] ?? "#6B6460";
                    return (
                      <tr
                        key={entry.id}
                        style={{
                          borderBottom: i < entries.length - 1 ? "1px solid var(--border-light)" : "none",
                        }}
                      >
                        <td
                          className="px-6 py-3 font-mono text-xs"
                          style={{ color: "var(--text-secondary)" }}
                        >
                          {entry.reference ?? `#${entry.id.slice(0, 8)}`}
                        </td>
                        <td className="px-6 py-3">
                          <span
                            className="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-semibold"
                            style={{
                              background: `${jColor}14`,
                              color: jColor,
                              border: `1px solid ${jColor}30`,
                            }}
                          >
                            {entry.journal_code}
                            <span
                              className="hidden sm:inline font-normal"
                              style={{ color: `${jColor}99` }}
                            >
                              {JOURNAL_LABELS[entry.journal_code] ?? ""}
                            </span>
                          </span>
                        </td>
                        <td
                          className="px-6 py-3 tabular-nums text-sm"
                          style={{ color: "var(--text-secondary)" }}
                        >
                          {new Date(entry.entry_date).toLocaleDateString("fr-FR")}
                        </td>
                        <td className="px-6 py-3">
                          <span
                            className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
                            style={{
                              background: badge.bg,
                              color: badge.color,
                              border: `1px solid ${badge.border}`,
                            }}
                          >
                            <span
                              className="h-1.5 w-1.5 rounded-full"
                              style={{ background: badge.color }}
                            />
                            {badge.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Financial summary — 1/3 */}
        <div className="flex flex-col gap-4">

          {/* Compte de résultat */}
          <div
            className="rounded-xl p-5"
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              boxShadow: "var(--shadow-sm)",
            }}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                Résultat {year}
              </h2>
              <Link
                href="/app/reports"
                className="text-xs"
                style={{ color: "var(--text-tertiary)" }}
              >
                Détail →
              </Link>
            </div>

            {resultat ? (
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span style={{ color: "var(--text-secondary)" }}>Produits</span>
                  <span
                    className="font-medium tabular-nums"
                    style={{ color: "var(--success)" }}
                  >
                    {formatAmount(resultat.produits.total)}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span style={{ color: "var(--text-secondary)" }}>Charges</span>
                  <span
                    className="font-medium tabular-nums"
                    style={{ color: "var(--danger)" }}
                  >
                    {formatAmount(resultat.charges.total)}
                  </span>
                </div>
                <div
                  className="pt-3 flex justify-between text-sm"
                  style={{ borderTop: "1px solid var(--border-light)" }}
                >
                  <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
                    Résultat net
                  </span>
                  <span
                    className="font-bold tabular-nums"
                    style={{
                      color: resultat.resultat_type === "benefice"
                        ? "var(--success)"
                        : "var(--danger)",
                    }}
                  >
                    {formatAmount(resultat.resultat_net)}
                  </span>
                </div>
                <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                  {resultat.resultat_type === "benefice" ? "Bénéfice" : "Perte"} de l&apos;exercice
                </p>
              </div>
            ) : (
              <div className="space-y-3 animate-pulse">
                <div className="h-4 rounded" style={{ background: "var(--border-light)" }} />
                <div className="h-4 rounded w-5/6" style={{ background: "var(--border-light)" }} />
                <div className="h-5 rounded w-2/3 mt-2" style={{ background: "var(--border-light)" }} />
              </div>
            )}
          </div>

          {/* TVA CA3 */}
          <div
            className="rounded-xl p-5"
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              boxShadow: "var(--shadow-sm)",
            }}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                TVA — CA3 {year}
              </h2>
              <Link
                href="/app/reports"
                className="text-xs"
                style={{ color: "var(--text-tertiary)" }}
              >
                Détail →
              </Link>
            </div>

            {tva ? (
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span style={{ color: "var(--text-secondary)" }}>Collectée</span>
                  <span
                    className="font-medium tabular-nums"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {formatAmount(tva.tva_collectee.total)}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span style={{ color: "var(--text-secondary)" }}>Déductible</span>
                  <span
                    className="font-medium tabular-nums"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {formatAmount(tva.tva_deductible.total)}
                  </span>
                </div>
                <div
                  className="pt-3 flex justify-between text-sm"
                  style={{ borderTop: "1px solid var(--border-light)" }}
                >
                  <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
                    {tva.resultat === "tva_a_payer"
                      ? "TVA à payer"
                      : tva.resultat === "credit_tva"
                      ? "Crédit de TVA"
                      : "Solde"}
                  </span>
                  <span
                    className="font-bold tabular-nums"
                    style={{
                      color:
                        tva.resultat === "tva_a_payer"
                          ? "var(--danger)"
                          : tva.resultat === "credit_tva"
                          ? "var(--success)"
                          : "var(--text-primary)",
                    }}
                  >
                    {formatAmount(tva.solde_net)}
                  </span>
                </div>
              </div>
            ) : (
              <div className="space-y-3 animate-pulse">
                <div className="h-4 rounded" style={{ background: "var(--border-light)" }} />
                <div className="h-4 rounded w-5/6" style={{ background: "var(--border-light)" }} />
                <div className="h-5 rounded w-2/3 mt-2" style={{ background: "var(--border-light)" }} />
              </div>
            )}
          </div>

          {/* AI activity hint */}
          <div
            className="rounded-xl p-4"
            style={{
              background: "var(--amber-50)",
              border: "1px solid var(--amber-200)",
            }}
          >
            <div className="flex items-start gap-3">
              <div
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg mt-0.5"
                style={{ background: "var(--amber-500)" }}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path
                    d="M7 2L8.5 5.5H12L9 7.5L10.5 11L7 9L3.5 11L5 7.5L2 5.5H5.5L7 2Z"
                    fill="#131110"
                  />
                </svg>
              </div>
              <div>
                <p className="text-xs font-semibold" style={{ color: "var(--amber-800)" }}>
                  Agent IA actif
                </p>
                <p className="text-xs mt-0.5" style={{ color: "var(--amber-700)" }}>
                  Analyse des documents en cours. Résultats disponibles sous peu.
                </p>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

