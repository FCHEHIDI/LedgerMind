"use client";

import { useState, useEffect, useCallback } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Invoice {
  id: string;
  reference: string;
  status: string;
  source_key: string;
  vendor_name: string;
  vendor_siren: string;
  ht_amount: string;
  tva_amount: string;
  ttc_amount: string;
  invoice_date: string | null;
  created_at: string;
  updated_at: string;
}

interface InvoiceListResponse {
  count?: number;
  results?: Invoice[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STATUSES = [
  { value: "", label: "Tous les statuts" },
  { value: "pending", label: "En attente" },
  { value: "processing", label: "Traitement IA…" },
  { value: "extracted", label: "À valider" },
  { value: "validated", label: "Validée" },
  { value: "rejected", label: "Rejetée" },
  { value: "error", label: "Erreur" },
];

const STATUS_LABELS: Record<string, string> = {
  pending: "En attente",
  processing: "Traitement IA…",
  extracted: "À valider",
  validated: "Validée",
  rejected: "Rejetée",
  error: "Erreur",
};

const STATUS_STYLES: Record<string, string> = {
  pending:
    "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  processing:
    "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-400",
  extracted:
    "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  validated:
    "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
  rejected:
    "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
  error:
    "bg-orange-50 text-orange-600 dark:bg-orange-950 dark:text-orange-400",
};

const STATUS_DOT: Record<string, string> = {
  pending: "bg-zinc-400",
  processing: "bg-blue-500",
  extracted: "bg-amber-500",
  validated: "bg-emerald-500",
  rejected: "bg-red-500",
  error: "bg-orange-500",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(val: string | null | undefined): string {
  if (!val) return "—";
  const n = parseFloat(val);
  if (isNaN(n)) return "—";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(n);
}

function fmtDate(val: string | null | undefined): string {
  if (!val) return "—";
  const d = new Date(val);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// ── New Invoice Modal ─────────────────────────────────────────────────────────

interface NewInvoiceModalProps {
  onClose: () => void;
  onCreated: () => void;
}

function NewInvoiceModal({ onClose, onCreated }: NewInvoiceModalProps) {
  const [form, setForm] = useState({
    reference: "",
    vendor_name: "",
    vendor_siren: "",
    ht_amount: "",
    tva_amount: "",
    ttc_amount: "",
    invoice_date: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const payload: Record<string, string> = {};
      Object.entries(form).forEach(([k, v]) => {
        if (v.trim()) payload[k] = v.trim();
      });
      const res = await fetch("/api/invoices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `Erreur ${res.status}`);
      }
      onCreated();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-zinc-900 shadow-2xl border border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-100 dark:border-zinc-800">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Nouvelle facture</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition-colors text-lg">✕</button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Row 1: reference + date */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Référence</label>
              <input
                type="text"
                value={form.reference}
                onChange={(e) => set("reference", e.target.value)}
                placeholder="FA-2024-001"
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Date facture</label>
              <input
                type="date"
                value={form.invoice_date}
                onChange={(e) => set("invoice_date", e.target.value)}
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              />
            </div>
          </div>
          {/* Row 2: vendor name + SIREN */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Fournisseur</label>
              <input
                type="text"
                value={form.vendor_name}
                onChange={(e) => set("vendor_name", e.target.value)}
                placeholder="Acme SARL"
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">SIREN</label>
              <input
                type="text"
                value={form.vendor_siren}
                onChange={(e) => set("vendor_siren", e.target.value)}
                placeholder="123456789"
                maxLength={9}
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400 font-mono"
              />
            </div>
          </div>
          {/* Row 3: HT / TVA / TTC */}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Montant HT</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.ht_amount}
                onChange={(e) => set("ht_amount", e.target.value)}
                placeholder="0.00"
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">TVA</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.tva_amount}
                onChange={(e) => set("tva_amount", e.target.value)}
                placeholder="0.00"
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">TTC</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.ttc_amount}
                onChange={(e) => set("ttc_amount", e.target.value)}
                placeholder="0.00"
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              />
            </div>
          </div>

          {error && <p className="text-sm text-red-500">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-4 py-2 text-sm text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
            >
              {loading ? "Création…" : "Créer la facture"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Invoice Drawer ──────────────────────────────────────────────────────────

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
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm" onClick={onClose} />
      {/* Panel */}
      <div className="fixed right-0 top-0 z-50 h-full w-full max-w-xl bg-white dark:bg-zinc-900 shadow-2xl flex flex-col border-l border-zinc-200 dark:border-zinc-800 overflow-hidden">
        {/* Header */}
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
          {/* Invoice summary */}
          <section>
            <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-3">Données extraites par l’IA</h3>
            <div className="grid grid-cols-2 gap-3">
              {([
                { label: "Fournisseur", value: invoice.vendor_name },
                { label: "SIREN", value: invoice.vendor_siren },
                { label: "Date facture", value: fmtDate(invoice.invoice_date) },
                { label: "Statut", value: STATUS_LABELS[invoice.status] ?? invoice.status },
                { label: "Montant HT", value: fmt(invoice.ht_amount) },
                { label: "TVA", value: fmt(invoice.tva_amount) },
                { label: "TTC", value: fmt(invoice.ttc_amount) },
              ] as { label: string; value: string }[]).map(({ label, value }) => (
                <div key={label} className="rounded-lg bg-zinc-50 dark:bg-zinc-800/60 px-3 py-2">
                  <p className="text-xs text-zinc-400 mb-0.5">{label}</p>
                  <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200 truncate">{value || "—"}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Journal entry */}
          <section>
            <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-3">Écriture comptable générée</h3>
            {loadingEntry ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-10 rounded-lg bg-zinc-100 dark:bg-zinc-800 animate-pulse" />
                ))}
              </div>
            ) : !entry ? (
              <div className="rounded-xl border border-dashed border-zinc-200 dark:border-zinc-700 px-4 py-6 text-center text-xs text-zinc-400">
                {invoice.status === "processing" ? "Traitement en cours…" : "Aucune écriture générée."}
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
                    <span className={`h-1.5 w-1.5 rounded-full ${
                      entry.status === "draft" ? "bg-amber-500" :
                      entry.status === "posted" ? "bg-emerald-500" : "bg-zinc-400"
                    }`} />
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
            <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
              {actionError}
            </div>
          )}
        </div>

        {/* Footer actions */}
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
              {actionLoading === "validate" ? "Validation…" : "Valider l’écriture"}
            </button>
          </div>
        )}
      </div>
    </>
  );
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

interface StatusCount {
  status: string;
  count: number;
}

function StatsBar({ invoices }: { invoices: Invoice[] }) {
  const counts = STATUSES.slice(1).map((s) => ({
    ...s,
    count: invoices.filter((i) => i.status === s.value).length,
  }));

  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
      {counts.map(({ value, label, count }) => (
        <div
          key={value}
          className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-4 py-3"
        >
          <div className="flex items-center gap-2 mb-1">
            <span className={`h-2 w-2 rounded-full ${STATUS_DOT[value]}`} />
            <span className="text-xs text-zinc-500 dark:text-zinc-400 truncate">{label}</span>
          </div>
          <p className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">{count}</p>
        </div>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

  // Modal / Drawer
  const [showModal, setShowModal] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (status) params.set("status", status);
      params.set("page", String(page));
      params.set("page_size", String(PAGE_SIZE));

      const res = await fetch(`/api/invoices?${params}`);
      if (!res.ok) throw new Error(`Erreur ${res.status}`);
      const data: InvoiceListResponse | Invoice[] = await res.json();
      if (Array.isArray(data)) {
        setInvoices(data);
        setTotal(data.length);
      } else {
        setInvoices(data.results ?? []);
        setTotal(data.count ?? 0);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, [search, status, page]);

  useEffect(() => {
    void load();
  }, [load]);

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [search, status]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Factures</h1>
          <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
            {total > 0 ? `${total} facture${total > 1 ? "s" : ""}` : "Aucune facture"}
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 transition-colors"
        >
          + Nouvelle facture
        </button>
      </div>

      {/* Stats */}
      {invoices.length > 0 && <StatsBar invoices={invoices} />}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          type="search"
          placeholder="Référence, fournisseur…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 w-60"
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
        >
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-14 rounded-xl bg-zinc-100 dark:bg-zinc-800 animate-pulse" />
          ))}
        </div>
      ) : invoices.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 py-20 gap-3 text-center">
          <div className="rounded-full bg-zinc-100 dark:bg-zinc-800 p-4 text-2xl">🧾</div>
          <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Aucune facture</p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-xs">
            {search || status
              ? "Aucun résultat pour ces filtres."
              : "Créez votre première facture ou importez des documents via le module Documents."}
          </p>
          {!search && !status && (
            <button
              onClick={() => setShowModal(true)}
              className="mt-2 rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 transition-colors"
            >
              + Nouvelle facture
            </button>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100 dark:border-zinc-800 text-xs text-zinc-500 dark:text-zinc-400">
                <th className="px-4 py-3 text-left font-medium">Référence</th>
                <th className="px-4 py-3 text-left font-medium">Fournisseur</th>
                <th className="px-4 py-3 text-left font-medium hidden sm:table-cell">SIREN</th>
                <th className="px-4 py-3 text-left font-medium hidden md:table-cell">Date</th>
                <th className="px-4 py-3 text-right font-medium">HT</th>
                <th className="px-4 py-3 text-right font-medium hidden sm:table-cell">TVA</th>
                <th className="px-4 py-3 text-right font-medium">TTC</th>
                <th className="px-4 py-3 text-left font-medium">Statut</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {invoices.map((inv) => (
                <tr
                  key={inv.id}
                  onClick={() => setSelectedInvoice(inv)}
                  className="hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors cursor-pointer"
                >
                  <td className="px-4 py-3 font-mono text-xs text-zinc-700 dark:text-zinc-300">
                    {inv.reference || <span className="text-zinc-400">—</span>}
                  </td>
                  <td className="px-4 py-3 text-zinc-800 dark:text-zinc-200 max-w-[160px] truncate">
                    {inv.vendor_name || <span className="text-zinc-400">—</span>}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-zinc-500 dark:text-zinc-400 hidden sm:table-cell">
                    {inv.vendor_siren || "—"}
                  </td>
                  <td className="px-4 py-3 text-zinc-500 dark:text-zinc-400 hidden md:table-cell whitespace-nowrap">
                    {fmtDate(inv.invoice_date)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-zinc-700 dark:text-zinc-300 whitespace-nowrap">
                    {fmt(inv.ht_amount)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-zinc-500 dark:text-zinc-400 whitespace-nowrap hidden sm:table-cell">
                    {fmt(inv.tva_amount)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs font-medium text-zinc-900 dark:text-zinc-100 whitespace-nowrap">
                    {fmt(inv.ttc_amount)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[inv.status] ?? STATUS_STYLES.pending}`}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[inv.status] ?? STATUS_DOT.pending}`} />
                      {STATUS_LABELS[inv.status] ?? inv.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-zinc-500 dark:text-zinc-400">
          <span>
            Page {page} / {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              ← Précédent
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Suivant →
            </button>
          </div>
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <NewInvoiceModal
          onClose={() => setShowModal(false)}
          onCreated={load}
        />
      )}

      {/* Invoice Drawer */}
      <InvoiceDrawer
        invoice={selectedInvoice}
        onClose={() => setSelectedInvoice(null)}
        onActionDone={load}
      />
    </div>
  );
}
