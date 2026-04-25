import { cookies } from "next/headers";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

interface DashboardMetrics {
  total_journal_entries: number;
  pending_entries: number;
  documents_count: number;
  compliance_alerts: number;
}

async function fetchMetrics(): Promise<DashboardMetrics | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) return null;

  try {
    const res = await fetch(`${API_BASE}/api/dashboard/metrics/`, {
      headers: { Authorization: `Bearer ${token}` },
      next: { revalidate: 60 }, // revalidate toutes les 60s
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function MetricCard({
  label,
  value,
  description,
}: {
  label: string;
  value: number | string;
  description?: string;
}) {
  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
      <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-2 text-3xl font-bold text-zinc-900 dark:text-zinc-50">{value}</p>
      {description && (
        <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">{description}</p>
      )}
    </div>
  );
}

export default async function DashboardPage() {
  const metrics = await fetchMetrics();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          Tableau de bord
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Vue d&apos;ensemble de votre activité comptable
        </p>
      </div>

      {metrics ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            label="Écritures totales"
            value={metrics.total_journal_entries}
          />
          <MetricCard
            label="En attente"
            value={metrics.pending_entries}
            description="Écritures à valider"
          />
          <MetricCard
            label="Documents"
            value={metrics.documents_count}
          />
          <MetricCard
            label="Alertes conformité"
            value={metrics.compliance_alerts}
            description="À traiter"
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {["Écritures totales", "En attente", "Documents", "Alertes conformité"].map(
            (label) => (
              <div
                key={label}
                className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm animate-pulse"
              >
                <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{label}</p>
                <div className="mt-2 h-9 w-16 rounded bg-zinc-100 dark:bg-zinc-800" />
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}
