import { cookies } from "next/headers";
import Link from "next/link";
import FecExportButton from "./FecExportButton";

const API_BASE =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

const JOURNAL_LABELS: Record<string, string> = {
  ACH: "Achats",
  VTE: "Ventes",
  BQ: "Banque",
  OD: "Opérations diverses",
  CAI: "Caisse",
};

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  posted: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
  cancelled: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Brouillon",
  posted: "Comptabilisé",
  cancelled: "Annulé",
};

interface AccountEntry {
  id: string;
  account_code: string;
  account_label: string;
  debit: string;
  credit: string;
}

interface JournalEntry {
  id: string;
  reference: string;
  journal_code: string;
  entry_date: string;
  status: "draft" | "posted" | "cancelled";
  lines: AccountEntry[];
  created_at: string;
}

interface PaginatedResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: JournalEntry[];
}

async function fetchJournal(): Promise<PaginatedResponse | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) return null;

  try {
    const res = await fetch(`${API_BASE}/api/v1/journal/`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function sumLines(lines: AccountEntry[], field: "debit" | "credit") {
  return lines
    .reduce((acc, l) => acc + parseFloat(l[field] || "0"), 0)
    .toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default async function LedgerPage() {
  const data = await fetchJournal();

  return (
    <div className="space-y-6">
      {/* En-tête */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
            Journal des écritures
          </h1>
          <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
            {data ? `${data.count} écriture${data.count !== 1 ? "s" : ""}` : "—"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <FecExportButton />
          <Link
            href="/app/ledger/new"
            className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 dark:bg-zinc-50 px-4 py-2 text-sm font-medium text-zinc-50 dark:text-zinc-900 hover:bg-zinc-700 dark:hover:bg-zinc-200 transition-colors"
          >
            + Nouvelle écriture
          </Link>
        </div>
      </div>

      {/* Tableau */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden">
        {!data || data.results.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <p className="text-zinc-400 dark:text-zinc-500 text-sm">
              Aucune écriture pour le moment.
            </p>
            <Link
              href="/app/ledger/new"
              className="mt-4 text-sm font-medium text-zinc-900 dark:text-zinc-50 underline underline-offset-4"
            >
              Créer la première écriture
            </Link>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/50">
                <th className="px-4 py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">
                  Date
                </th>
                <th className="px-4 py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">
                  Référence
                </th>
                <th className="px-4 py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">
                  Journal
                </th>
                <th className="px-4 py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">
                  Statut
                </th>
                <th className="px-4 py-3 text-right font-medium text-zinc-500 dark:text-zinc-400">
                  Débit (€)
                </th>
                <th className="px-4 py-3 text-right font-medium text-zinc-500 dark:text-zinc-400">
                  Crédit (€)
                </th>
                <th className="px-4 py-3 text-center font-medium text-zinc-500 dark:text-zinc-400">
                  Lignes
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {data.results.map((entry) => (
                <tr
                  key={entry.id}
                  className="hover:bg-zinc-50 dark:hover:bg-zinc-800/40 transition-colors"
                >
                  <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300 tabular-nums">
                    {formatDate(entry.entry_date)}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/app/ledger/${entry.id}`}
                      className="font-medium text-zinc-900 dark:text-zinc-50 hover:underline"
                    >
                      {entry.reference || <span className="text-zinc-400">—</span>}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    <span className="font-mono text-xs bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">
                      {entry.journal_code}
                    </span>
                    <span className="ml-2 text-zinc-500 dark:text-zinc-500">
                      {JOURNAL_LABELS[entry.journal_code] ?? entry.journal_code}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[entry.status] ?? ""}`}
                    >
                      {STATUS_LABELS[entry.status] ?? entry.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-zinc-700 dark:text-zinc-300">
                    {sumLines(entry.lines, "debit")}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-zinc-700 dark:text-zinc-300">
                    {sumLines(entry.lines, "credit")}
                  </td>
                  <td className="px-4 py-3 text-center text-zinc-500 dark:text-zinc-400">
                    {entry.lines.length}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
