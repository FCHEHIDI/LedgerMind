import { cookies } from "next/headers";
import DocumentsClient from "./DocumentsClient";

const API_BASE =
  process.env.DJANGO_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://api.localhost:8888";

const STATUS_LABELS: Record<string, string> = {
  pending: "En attente",
  processing: "Traitement…",
  extracted: "Extrait",
  validated: "Validé",
  rejected: "Rejeté",
  error: "Erreur",
};

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  processing: "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-400 animate-pulse",
  extracted: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  validated: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
  rejected: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
  error: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
};

interface Invoice {
  id: string;
  status: string;
  vendor_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  ttc_amount: string | null;
  created_at: string;
}

interface PaginatedResponse {
  count: number;
  results: Invoice[];
}

async function fetchInvoices(token: string): Promise<Invoice[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/invoices/`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return [];
    const data: PaginatedResponse = await res.json();
    return data.results ?? [];
  } catch {
    return [];
  }
}

/**
 * Server Component — Documents page.
 * Lists invoices fetched from Django + renders the client upload form.
 */
export default async function DocumentsPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value ?? "";

  const invoices = await fetchInvoices(token);

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
            Documents
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
            Importez une facture PDF pour lancer le traitement automatique par les
            agents IA.
          </p>
        </div>
        {invoices.some((inv) => ["pending", "processing"].includes(inv.status)) && (
          <span className="flex items-center gap-1.5 rounded-full bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 px-3 py-1 text-xs font-medium text-blue-700 dark:text-blue-400">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
            </span>
            Traitement en cours…
          </span>
        )}
      </div>

      {/* Upload zone (Client Component) — hasPending drives auto-polling */}
      <DocumentsClient hasPending={invoices.some((inv) => ["pending", "processing"].includes(inv.status))} />

      {/* Invoice list */}
      {invoices.length === 0 ? (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-6 py-10 text-center">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Aucun document importé pour le moment.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
          <table className="w-full text-sm">
            <thead className="border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-zinc-600 dark:text-zinc-400">
                  Fournisseur
                </th>
                <th className="px-4 py-3 text-left font-medium text-zinc-600 dark:text-zinc-400">
                  N° facture
                </th>
                <th className="px-4 py-3 text-left font-medium text-zinc-600 dark:text-zinc-400">
                  Date
                </th>
                <th className="px-4 py-3 text-right font-medium text-zinc-600 dark:text-zinc-400">
                  TTC
                </th>
                <th className="px-4 py-3 text-left font-medium text-zinc-600 dark:text-zinc-400">
                  Statut
                </th>
                <th className="px-4 py-3 text-left font-medium text-zinc-600 dark:text-zinc-400">
                  Importé le
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {invoices.map((inv) => (
                <tr
                  key={inv.id}
                  className="hover:bg-zinc-50 dark:hover:bg-zinc-800/30 transition-colors"
                >
                  <td className="px-4 py-3 text-zinc-900 dark:text-zinc-100">
                    {inv.vendor_name ?? (
                      <span className="text-zinc-400 italic">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    {inv.invoice_number ?? (
                      <span className="text-zinc-400 italic">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    {inv.invoice_date
                      ? new Date(inv.invoice_date).toLocaleDateString("fr-FR")
                      : <span className="text-zinc-400 italic">—</span>}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-zinc-900 dark:text-zinc-100">
                    {inv.ttc_amount
                      ? `${parseFloat(inv.ttc_amount).toLocaleString("fr-FR", { minimumFractionDigits: 2 })} €`
                      : <span className="text-zinc-400 italic">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[inv.status] ?? STATUS_STYLES.error}`}
                    >
                      {STATUS_LABELS[inv.status] ?? inv.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-zinc-500 dark:text-zinc-400">
                    {new Date(inv.created_at).toLocaleDateString("fr-FR")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
