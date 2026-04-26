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

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  draft: {
    label: "Brouillon",
    className: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  },
  posted: {
    label: "Validée",
    className: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  },
  cancelled: {
    label: "Annulée",
    className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
};

const JOURNAL_LABELS: Record<string, string> = {
  ACH: "Achats",
  VTE: "Ventes",
  BQ: "Banque",
  OD: "OD",
  AN: "À-nouveaux",
  PAI: "Paiements",
};

// ── UI Components ─────────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  description,
  accent,
}: {
  label: string;
  value: number | string;
  description?: string;
  accent?: "neutral" | "warning" | "danger" | "success";
}) {
  const accentClass =
    accent === "warning"
      ? "border-l-4 border-l-amber-400"
      : accent === "danger"
      ? "border-l-4 border-l-red-400"
      : accent === "success"
      ? "border-l-4 border-l-emerald-400"
      : "";

  return (
    <div
      className={`rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm ${accentClass}`}
    >
      <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-2 text-3xl font-bold text-zinc-900 dark:text-zinc-50">{value}</p>
      {description && (
        <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">{description}</p>
      )}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm animate-pulse">
      <div className="h-4 w-28 rounded bg-zinc-100 dark:bg-zinc-800" />
      <div className="mt-3 h-9 w-16 rounded bg-zinc-100 dark:bg-zinc-800" />
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function DashboardPage() {
  const token = await getToken();
  const year = new Date().getFullYear();

  if (!token) {
    return (
      <div className="flex items-center justify-center h-64 text-zinc-400 text-sm">
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
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          Tableau de bord
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
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
        <div className="lg:col-span-2 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-100 dark:border-zinc-800">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              Dernières écritures
            </h2>
            <Link
              href="/app/ledger"
              className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
            >
              Voir tout →
            </Link>
          </div>

          {entries.length === 0 ? (
            <div className="px-6 py-10 text-center text-sm text-zinc-400">
              Aucune écriture enregistrée pour le moment.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-100 dark:border-zinc-800">
                    <th className="px-6 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">
                      Référence
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">
                      Journal
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">
                      Date
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">
                      Statut
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                  {entries.map((entry) => {
                    const badge = STATUS_BADGE[entry.status] ?? STATUS_BADGE.draft;
                    return (
                      <tr
                        key={entry.id}
                        className="hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors"
                      >
                        <td className="px-6 py-3 font-mono text-xs text-zinc-700 dark:text-zinc-300">
                          {entry.reference ?? `#${entry.id.slice(0, 8)}`}
                        </td>
                        <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                          <span className="inline-flex items-center gap-1">
                            <span className="font-medium">{entry.journal_code}</span>
                            <span className="text-zinc-400 text-xs hidden sm:inline">
                              — {JOURNAL_LABELS[entry.journal_code] ?? ""}
                            </span>
                          </span>
                        </td>
                        <td className="px-4 py-3 text-zinc-500 dark:text-zinc-400 tabular-nums">
                          {new Date(entry.entry_date).toLocaleDateString("fr-FR")}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}
                          >
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

          {/* Compte de résultat summary */}
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Résultat {year}
              </h2>
              <Link
                href="/app/reports"
                className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
              >
                Détail →
              </Link>
            </div>

            {resultat ? (
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-zinc-500">Produits</span>
                  <span className="font-medium text-emerald-600 dark:text-emerald-400 tabular-nums">
                    {formatAmount(resultat.produits.total)}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-zinc-500">Charges</span>
                  <span className="font-medium text-red-500 dark:text-red-400 tabular-nums">
                    {formatAmount(resultat.charges.total)}
                  </span>
                </div>
                <div className="border-t border-zinc-100 dark:border-zinc-800 pt-3 flex justify-between text-sm">
                  <span className="font-semibold text-zinc-700 dark:text-zinc-300">
                    Résultat net
                  </span>
                  <span
                    className={`font-bold tabular-nums ${
                      resultat.resultat_type === "benefice"
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-red-500 dark:text-red-400"
                    }`}
                  >
                    {formatAmount(resultat.resultat_net)}
                  </span>
                </div>
                <p className="text-xs text-zinc-400 capitalize">
                  {resultat.resultat_type === "benefice" ? "Bénéfice" : "Perte"} de l&apos;exercice
                </p>
              </div>
            ) : (
              <div className="space-y-3 animate-pulse">
                <div className="h-4 bg-zinc-100 dark:bg-zinc-800 rounded w-full" />
                <div className="h-4 bg-zinc-100 dark:bg-zinc-800 rounded w-5/6" />
                <div className="h-5 bg-zinc-100 dark:bg-zinc-800 rounded w-2/3 mt-2" />
              </div>
            )}
          </div>

          {/* TVA summary */}
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                TVA — CA3 {year}
              </h2>
              <Link
                href="/app/reports"
                className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
              >
                Détail →
              </Link>
            </div>

            {tva ? (
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-zinc-500">Collectée</span>
                  <span className="font-medium tabular-nums text-zinc-700 dark:text-zinc-300">
                    {formatAmount(tva.tva_collectee.total)}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-zinc-500">Déductible</span>
                  <span className="font-medium tabular-nums text-zinc-700 dark:text-zinc-300">
                    {formatAmount(tva.tva_deductible.total)}
                  </span>
                </div>
                <div className="border-t border-zinc-100 dark:border-zinc-800 pt-3 flex justify-between text-sm">
                  <span className="font-semibold text-zinc-700 dark:text-zinc-300">
                    {tva.resultat === "tva_a_payer"
                      ? "TVA à payer"
                      : tva.resultat === "credit_tva"
                      ? "Crédit de TVA"
                      : "Solde"}
                  </span>
                  <span
                    className={`font-bold tabular-nums ${
                      tva.resultat === "tva_a_payer"
                        ? "text-red-500 dark:text-red-400"
                        : tva.resultat === "credit_tva"
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-zinc-700 dark:text-zinc-300"
                    }`}
                  >
                    {formatAmount(tva.solde_net)}
                  </span>
                </div>
              </div>
            ) : (
              <div className="space-y-3 animate-pulse">
                <div className="h-4 bg-zinc-100 dark:bg-zinc-800 rounded w-full" />
                <div className="h-4 bg-zinc-100 dark:bg-zinc-800 rounded w-5/6" />
                <div className="h-5 bg-zinc-100 dark:bg-zinc-800 rounded w-2/3 mt-2" />
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
