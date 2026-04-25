import Link from "next/link";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import ValidateButtons from "./ValidateButtons";

const API_BASE =
  process.env.DJANGO_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://api.localhost:8888";

const JOURNAL_LABELS: Record<string, string> = {
  ACH: "Achats",
  VTE: "Ventes",
  BQ: "Banque",
  OD: "Opérations diverses",
  CAI: "Caisse",
};

const STATUS_STYLES: Record<string, string> = {
  draft:
    "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  posted:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400",
  cancelled:
    "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Brouillon",
  posted: "Validé",
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
  status: string;
  invoice: string | null;
  created_at: string;
  lines: AccountEntry[];
}

function fmt(val: string): string {
  const n = parseFloat(val);
  if (isNaN(n)) return "—";
  return n.toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export default async function JournalEntryDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;

  if (!token) {
    notFound();
  }

  const res = await fetch(`${API_BASE}/api/v1/journal/${id}/`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  if (res.status === 404) notFound();
  if (!res.ok) {
    throw new Error(`Erreur ${res.status} lors du chargement de l'écriture.`);
  }

  const entry: JournalEntry = await res.json();

  const totalDebit = entry.lines.reduce(
    (s, l) => s + parseFloat(l.debit || "0"),
    0
  );
  const totalCredit = entry.lines.reduce(
    (s, l) => s + parseFloat(l.credit || "0"),
    0
  );

  const journalLabel = JOURNAL_LABELS[entry.journal_code] ?? entry.journal_code;
  const statusStyle =
    STATUS_STYLES[entry.status] ?? STATUS_STYLES.draft;
  const statusLabel = STATUS_LABELS[entry.status] ?? entry.status;

  return (
    <div className="space-y-6 max-w-4xl">
      {/* En-tête */}
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href="/app/ledger"
          className="text-sm text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
        >
          ← Retour
        </Link>
        <span className="text-zinc-300 dark:text-zinc-700">/</span>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          {entry.reference || "Écriture sans référence"}
        </h1>
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusStyle}`}
        >
          {statusLabel}
        </span>
        {entry.status === "draft" && (
          <div className="ml-auto">
            <ValidateButtons entryId={entry.id} />
          </div>
        )}
      </div>

      {/* Métadonnées */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6">
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Date
            </p>
            <p className="mt-1 text-sm font-medium text-zinc-900 dark:text-zinc-50">
              {fmtDate(entry.entry_date)}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Journal
            </p>
            <p className="mt-1 text-sm font-medium text-zinc-900 dark:text-zinc-50">
              <span className="font-mono">{entry.journal_code}</span>
              {" — "}
              {journalLabel}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Référence
            </p>
            <p className="mt-1 text-sm font-medium text-zinc-900 dark:text-zinc-50">
              {entry.reference || <span className="text-zinc-400">—</span>}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Créé le
            </p>
            <p className="mt-1 text-sm font-medium text-zinc-900 dark:text-zinc-50">
              {fmtDate(entry.created_at)}
            </p>
          </div>
        </div>
      </div>

      {/* Lignes */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden">
        <div className="px-6 py-4 border-b border-zinc-100 dark:border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Lignes d'écriture
            <span className="ml-2 text-xs font-normal text-zinc-400">
              ({entry.lines.length} ligne{entry.lines.length > 1 ? "s" : ""})
            </span>
          </h2>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="bg-zinc-50 dark:bg-zinc-800/50 border-b border-zinc-100 dark:border-zinc-800">
              <th className="px-4 py-2 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide w-28">
                Compte PCG
              </th>
              <th className="px-4 py-2 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">
                Libellé
              </th>
              <th className="px-4 py-2 text-right text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide w-32">
                Débit (€)
              </th>
              <th className="px-4 py-2 text-right text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide w-32">
                Crédit (€)
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {entry.lines.map((line) => (
              <tr key={line.id} className="hover:bg-zinc-50/50 dark:hover:bg-zinc-800/30">
                <td className="px-4 py-3 font-mono text-sm text-zinc-900 dark:text-zinc-50">
                  {line.account_code}
                </td>
                <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                  {line.account_label || (
                    <span className="text-zinc-400">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-zinc-900 dark:text-zinc-50">
                  {parseFloat(line.debit) > 0 ? fmt(line.debit) : (
                    <span className="text-zinc-300 dark:text-zinc-600">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-zinc-900 dark:text-zinc-50">
                  {parseFloat(line.credit) > 0 ? fmt(line.credit) : (
                    <span className="text-zinc-300 dark:text-zinc-600">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/50">
              <td
                colSpan={2}
                className="px-4 py-3 text-right text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide"
              >
                Total
              </td>
              <td className="px-4 py-3 text-right tabular-nums font-semibold text-zinc-900 dark:text-zinc-50">
                {totalDebit.toLocaleString("fr-FR", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </td>
              <td className="px-4 py-3 text-right tabular-nums font-semibold text-zinc-900 dark:text-zinc-50">
                {totalCredit.toLocaleString("fr-FR", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Pied de page — UUID technique */}
      <p className="text-xs text-zinc-400 dark:text-zinc-600 font-mono">
        ID : {entry.id}
      </p>
    </div>
  );
}
