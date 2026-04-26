"use client";

import { useState, useEffect, useCallback } from "react";
import UploadForm from "./UploadForm";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Invoice {
  id: string;
  reference: string;
  status: string;
  vendor_name: string | null;
  invoice_date: string | null;
  ttc_amount: string | null;
  created_at: string;
}

interface AccountEntryLine {
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
  lines: AccountEntryLine[];
}

// ── Status config ─────────────────────────────────────────────────────────────

const STATUS_LABELS: Record<string, string> = {
  pending: "En file d'attente",
  processing: "Traitement IA…",
  extracted: "À valider",
  validated: "Validée",
  rejected: "Rejetée",
  error: "Erreur",
};

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  processing: "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-400",
  extracted: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  validated: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
  rejected: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
  error: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(val: string | null | undefined): string {
  if (!val) return "—";
  const n = parseFloat(val);
  if (isNaN(n)) return "—";
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", minimumFractionDigits: 2 }).format(n);
}

function fmtDate(val: string | null | undefined): string {
  if (!val) return "—";
  const d = new Date(val);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// ── Invoice Drawer ────────────────────────────────────────────────────────────

interface InvoiceDrawerProps {
  invoice: Invoice | null;
  onClose: () => void;
  onActionDone: () => void;
}

function InvoiceDrawer({ invoice, onClose, onActionDone }: InvoiceDrawerProps) {
  const [entry, setEntry] = useState<JournalEntry | null>(null);
  const [loadingEntry, setLoadingEntry] = useState(false);
  const [actionLoading, setActionLoading] = useState<"validate" | "cancel" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!invoice) return;
    setEntry(null);
    setActionError(null);
    setLoadingEntry(true);
    fetch(`/api/journal?invoice=${invoice.id}`)
      .then((r) => r.json())
      .then((data) => {
        const results: JournalEntry[] = Array.isArray(data) ? data : (data.results ?? []);
        setEntry(results[0] ?? null);
      })
      .catch(() => setEntry(null))
      .finally(() => setLoadingEntry(false));
  }, [invoice]);

  async function handleAction(action: "validate" | "cancel") {
    if (!entry) return;
    setActionLoading(action);
    setActionError(null);
    try {
      const res = await fetch(`/api/journal/${entry.id}/${action}`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error((data as { detail?: string; error?: string }).detail ?? (data as { detail?: string; error?: string }).error ?? `Erreur ${res.status}`);
      onActionDone();
      onClose();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setActionLoading(null);
    }
  }

  if (!invoice) return null;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 z-50 h-full w-full max-w-xl bg-white dark:bg-zinc-900 shadow-2xl flex flex-col border-l border-zinc-200 dark:border-zinc-800 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-100 dark:border-zinc-800 shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              Facture — {invoice.reference || <span className="text-zinc-400 font-normal">sans référence</span>}
            </h2>
            <p className="text-xs text-zinc-500 mt-0.5">{invoice.vendor_name || "Fournisseur inconnu"}</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition-colors text-lg">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          <section>
            <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-3">Données extraites par l'IA</h3>
            <div className="grid grid-cols-2 gap-3">
              {([
                { label: "Fournisseur", value: invoice.vendor_name },
                { label: "Date facture", value: fmtDate(invoice.invoice_date) },
                { label: "TTC", value: fmt(invoice.ttc_amount) },
                { label: "Statut", value: STATUS_LABELS[invoice.status] ?? invoice.status },
              ] as { label: string; value: string }[]).map(({ label, value }) => (
                <div key={label} className="rounded-lg bg-zinc-50 dark:bg-zinc-800/60 px-3 py-2">
                  <p className="text-xs text-zinc-400 mb-0.5">{label}</p>
                  <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200 truncate">{value || "—"}</p>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-3">Écriture comptable générée</h3>
            {loadingEntry ? (
              <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-10 rounded-lg bg-zinc-100 dark:bg-zinc-800 animate-pulse" />)}</div>
            ) : !entry ? (
              <div className="rounded-xl border border-dashed border-zinc-200 dark:border-zinc-700 px-4 py-6 text-center text-xs text-zinc-400">
                {invoice.status === "processing" ? "Traitement IA en cours…" : "Aucune écriture générée."}
              </div>
            ) : (
              <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2.5 bg-zinc-50 dark:bg-zinc-800/50 border-b border-zinc-100 dark:border-zinc-800">
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-mono text-zinc-500">{entry.reference || entry.id.slice(0, 8)}</span>
                    <span className="text-xs text-zinc-400">{entry.journal_code} · {fmtDate(entry.entry_date)}</span>
                  </div>
                  <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${
                    entry.status === "draft" ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400" :
                    entry.status === "posted" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400" :
                    "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
                  }`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${entry.status === "draft" ? "bg-amber-500" : entry.status === "posted" ? "bg-emerald-500" : "bg-zinc-400"}`} />
                    {entry.status === "draft" ? "Brouillon" : entry.status === "posted" ? "Validée" : entry.status}
                  </span>
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-zinc-400 border-b border-zinc-100 dark:border-zinc-800">
                      <th className="px-4 py-2 text-left font-medium">Compte</th>
                      <th className="px-4 py-2 text-left font-medium">Libellé</th>
                      <th className="px-4 py-2 text-right font-medium">Débit</th>
                      <th className="px-4 py-2 text-right font-medium">Crédit</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                    {entry.lines.map((line) => (
                      <tr key={line.id} className="text-zinc-700 dark:text-zinc-300">
                        <td className="px-4 py-2 font-mono">{line.account_code}</td>
                        <td className="px-4 py-2 text-zinc-500 dark:text-zinc-400 max-w-[140px] truncate">{line.account_label}</td>
                        <td className="px-4 py-2 text-right font-mono">{parseFloat(line.debit) > 0 ? fmt(line.debit) : ""}</td>
                        <td className="px-4 py-2 text-right font-mono">{parseFloat(line.credit) > 0 ? fmt(line.credit) : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {actionError && (
            <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">{actionError}</div>
          )}
        </div>

        {entry?.status === "draft" && (
          <div className="shrink-0 px-6 py-4 border-t border-zinc-100 dark:border-zinc-800 flex gap-3">
            <button
              onClick={() => handleAction("cancel")}
              disabled={actionLoading !== null}
              className="flex-1 rounded-lg border border-red-200 dark:border-red-800 px-4 py-2.5 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20 disabled:opacity-40 transition-colors"
            >
              {actionLoading === "cancel" ? "Annulation…" : "Rejeter"}
            </button>
            <button
              onClick={() => handleAction("validate")}
              disabled={actionLoading !== null}
              className="flex-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2.5 text-sm font-medium disabled:opacity-40 transition-colors"
            >
              {actionLoading === "validate" ? "Validation…" : "Valider l'écriture"}
            </button>
          </div>
        )}
      </div>
    </>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

// ── Phase banner (priority-ordered) ─────────────────────────────────────────
// uploading  → "Chargement du document…"   (file POST in flight)
// processing → "Traitement IA en cours…"   (invoice pending/processing)
// to_validate → "X facture(s) à valider"    (invoice extracted)
// idle       → no banner

export default function DocumentsClient() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);
  /** True from the moment the user triggers upload until the server responds. */
  const [isUploading, setIsUploading] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/invoices?page_size=50");
      if (!res.ok) return;
      const data = await res.json();
      setInvoices(Array.isArray(data) ? data : (data.results ?? []));
    } finally {
      setInitialLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => { load(); }, [load]);

  // Poll every 2s while uploading or any invoice is in a transient state.
  // Only count invoices created within the last 30 min as "active" —
  // anything older is a ghost from a failed run and should not trigger the banner.
  const ACTIVE_WINDOW_MS = 30 * 60 * 1000;
  const hasPending = invoices.some((inv) => {
    if (!["pending", "processing"].includes(inv.status)) return false;
    const age = Date.now() - new Date(inv.created_at).getTime();
    return age < ACTIVE_WINDOW_MS;
  });
  useEffect(() => {
    if (!isUploading && !hasPending) return;
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [isUploading, hasPending, load]);

  const pendingValidation = invoices.filter((inv) => inv.status === "extracted").length;

  return (
    <div className="space-y-6">
      {/* ── Priority banner — hidden until first fetch completes ─────────── */}
      {/* Priority 1: file upload in flight */}
      {isUploading && (
        <div className="flex items-center gap-2.5 rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/40 px-4 py-2.5">
          <svg className="h-4 w-4 animate-spin text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          <span className="text-sm font-medium text-blue-700 dark:text-blue-300">Chargement du document…</span>
        </div>
      )}

      {/* Priority 2: AI agents running (invoice pending or processing) */}
      {!initialLoading && !isUploading && hasPending && (
        <div className="flex items-center gap-2.5 rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/40 px-4 py-2.5">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500" />
          </span>
          <span className="text-sm font-medium text-blue-700 dark:text-blue-300">Traitement IA en cours…</span>
        </div>
      )}

      {/* Priority 3: at least one invoice awaiting validation */}
      {!initialLoading && pendingValidation > 0 && (
        <div className="flex items-center gap-2.5 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 px-4 py-2.5">
          <span className="text-amber-500">⚠</span>
          <span className="text-sm font-medium text-amber-700 dark:text-amber-300">
            {pendingValidation} facture{pendingValidation > 1 ? "s" : ""} à valider — cliquez sur une ligne
          </span>
        </div>
      )}

      {/* Priority 4: idle — system ready, nothing in flight */}
      {!initialLoading && !isUploading && !hasPending && pendingValidation === 0 && (
        <div className="flex items-center gap-2.5 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/40 px-4 py-2.5">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          <span className="text-sm font-medium text-zinc-500 dark:text-zinc-400">Prêt — déposez une facture pour lancer le traitement</span>
        </div>
      )}

      {/* Upload zone */}
      <UploadForm
        onUploadStart={() => setIsUploading(true)}
        onSuccess={() => {
          // File accepted by server → clear upload phase, refresh list immediately.
          // The invoice will appear as "pending" on the next poll cycle (≤2s).
          setIsUploading(false);
          load();
        }}
      />

      {/* Invoice list */}
      {initialLoading ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-12 rounded-xl bg-zinc-100 dark:bg-zinc-800 animate-pulse" />)}</div>
      ) : invoices.length === 0 ? (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-6 py-10 text-center">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Aucun document importé pour le moment.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
          <table className="w-full text-sm">
            <thead className="border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-zinc-600 dark:text-zinc-400">Fournisseur</th>
                <th className="px-4 py-3 text-left font-medium text-zinc-600 dark:text-zinc-400">Référence</th>
                <th className="px-4 py-3 text-left font-medium text-zinc-600 dark:text-zinc-400">Date</th>
                <th className="px-4 py-3 text-right font-medium text-zinc-600 dark:text-zinc-400">TTC</th>
                <th className="px-4 py-3 text-left font-medium text-zinc-600 dark:text-zinc-400">Statut</th>
                <th className="px-4 py-3 text-left font-medium text-zinc-600 dark:text-zinc-400">Importé le</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {invoices.map((inv) => {
                const clickable = ["extracted", "validated", "rejected"].includes(inv.status);
                return (
                  <tr
                    key={inv.id}
                    onClick={() => clickable && setSelectedInvoice(inv)}
                    className={`transition-colors ${clickable ? "cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/50" : "hover:bg-zinc-50/50 dark:hover:bg-zinc-800/20"}`}
                  >
                    <td className="px-4 py-3 text-zinc-900 dark:text-zinc-100">{inv.vendor_name ?? <span className="text-zinc-400 italic">—</span>}</td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400 font-mono text-xs">{inv.reference || <span className="text-zinc-400 italic">—</span>}</td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">{fmtDate(inv.invoice_date)}</td>
                    <td className="px-4 py-3 text-right font-mono text-zinc-900 dark:text-zinc-100">{fmt(inv.ttc_amount)}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[inv.status] ?? STATUS_STYLES.error}`}>
                        {inv.status === "processing" && (
                          <span className="relative flex h-1.5 w-1.5">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500" />
                          </span>
                        )}
                        {STATUS_LABELS[inv.status] ?? inv.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-zinc-500 dark:text-zinc-400">{fmtDate(inv.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Drawer */}
      <InvoiceDrawer
        invoice={selectedInvoice}
        onClose={() => setSelectedInvoice(null)}
        onActionDone={load}
      />
    </div>
  );
}
