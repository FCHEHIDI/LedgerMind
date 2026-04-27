"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Receipt } from "lucide-react";

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

const STATUS_CONFIG: Record<string, { color: string; bg: string; border: string; dot: string }> = {
  pending:    { color: "var(--text-tertiary)", bg: "var(--bg-root)",    border: "var(--border)",          dot: "var(--text-tertiary)" },
  processing: { color: "#2563EB",              bg: "#EFF6FF",           border: "#BFDBFE",                dot: "#3B82F6" },
  extracted:  { color: "var(--warning)",       bg: "var(--warning-bg)", border: "var(--warning-border)",  dot: "var(--warning)" },
  validated:  { color: "var(--success)",       bg: "var(--success-bg)", border: "var(--success-border)",  dot: "var(--success)" },
  rejected:   { color: "var(--danger)",        bg: "var(--danger-bg)",  border: "var(--danger-border)",   dot: "var(--danger)" },
  error:      { color: "var(--danger)",        bg: "var(--danger-bg)",  border: "var(--danger-border)",   dot: "var(--danger)" },
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

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium"
      style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      {status === "processing" ? (
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: cfg.dot }} />
          <span className="relative inline-flex rounded-full h-1.5 w-1.5" style={{ background: cfg.dot }} />
        </span>
      ) : (
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: cfg.dot }} />
      )}
      {STATUS_LABELS[status] ?? status}
    </span>
  );
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
      <div
        className="w-full max-w-lg rounded-2xl"
        style={{ background: "var(--bg-card)", border: "1px solid var(--border)", boxShadow: "var(--shadow-md)" }}
      >
        <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: "1px solid var(--border-light)" }}>
          <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Nouvelle facture</h2>
          <button onClick={onClose} className="text-lg transition-colors" style={{ color: "var(--text-tertiary)" }}>✕</button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Row 1: reference + date */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>Référence</label>
              <input
                type="text"
                value={form.reference}
                onChange={(e) => set("reference", e.target.value)}
                placeholder="FA-2024-001"
                className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                style={{ background: "var(--bg-root)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                onFocus={(e) => { e.target.style.border = "1px solid var(--amber-400)"; e.target.style.boxShadow = "0 0 0 3px rgba(245,158,11,0.12)"; }}
                onBlur={(e) => { e.target.style.border = "1px solid var(--border)"; e.target.style.boxShadow = "none"; }}
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>Date facture</label>
              <input
                type="date"
                value={form.invoice_date}
                onChange={(e) => set("invoice_date", e.target.value)}
                className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                style={{ background: "var(--bg-root)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                onFocus={(e) => { e.target.style.border = "1px solid var(--amber-400)"; e.target.style.boxShadow = "0 0 0 3px rgba(245,158,11,0.12)"; }}
                onBlur={(e) => { e.target.style.border = "1px solid var(--border)"; e.target.style.boxShadow = "none"; }}
              />
            </div>
          </div>
          {/* Row 2: vendor name + SIREN */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>Fournisseur</label>
              <input
                type="text"
                value={form.vendor_name}
                onChange={(e) => set("vendor_name", e.target.value)}
                placeholder="Acme SARL"
                className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                style={{ background: "var(--bg-root)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                onFocus={(e) => { e.target.style.border = "1px solid var(--amber-400)"; e.target.style.boxShadow = "0 0 0 3px rgba(245,158,11,0.12)"; }}
                onBlur={(e) => { e.target.style.border = "1px solid var(--border)"; e.target.style.boxShadow = "none"; }}
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>SIREN</label>
              <input
                type="text"
                value={form.vendor_siren}
                onChange={(e) => set("vendor_siren", e.target.value)}
                placeholder="123456789"
                maxLength={9}
                className="w-full rounded-lg px-3 py-2 text-sm outline-none font-mono"
                style={{ background: "var(--bg-root)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                onFocus={(e) => { e.target.style.border = "1px solid var(--amber-400)"; e.target.style.boxShadow = "0 0 0 3px rgba(245,158,11,0.12)"; }}
                onBlur={(e) => { e.target.style.border = "1px solid var(--border)"; e.target.style.boxShadow = "none"; }}
              />
            </div>
          </div>
          {/* Row 3: HT / TVA / TTC */}
          <div className="grid grid-cols-3 gap-4">
            {(["ht_amount", "tva_amount", "ttc_amount"] as const).map((field, i) => (
              <div key={field}>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>
                  {["Montant HT", "TVA", "TTC"][i]}
                </label>
                <input
                  type="number" step="0.01" min="0"
                  value={form[field]}
                  onChange={(e) => set(field, e.target.value)}
                  placeholder="0.00"
                  className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                  style={{ background: "var(--bg-root)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                  onFocus={(e) => { e.target.style.border = "1px solid var(--amber-400)"; e.target.style.boxShadow = "0 0 0 3px rgba(245,158,11,0.12)"; }}
                  onBlur={(e) => { e.target.style.border = "1px solid var(--border)"; e.target.style.boxShadow = "none"; }}
                />
              </div>
            ))}
          </div>

          {error && <p className="text-sm" style={{ color: "var(--danger)" }}>{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-sm transition-colors"
              style={{ color: "var(--text-secondary)" }}
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg px-4 py-2 text-sm font-medium transition-all disabled:opacity-50 text-white"
              style={{ background: "var(--amber-600)", boxShadow: "var(--shadow-amber)" }}
              onMouseEnter={(e) => { if (!loading) e.currentTarget.style.background = "var(--amber-700)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "var(--amber-600)"; }}
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

  const entryCfg = entry ? (STATUS_CONFIG[entry.status] ?? STATUS_CONFIG.pending) : null;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm" onClick={onClose} />
      <div
        className="fixed right-0 top-0 z-50 h-full w-full max-w-xl flex flex-col overflow-hidden"
        style={{ background: "var(--bg-card)", borderLeft: "1px solid var(--border)", boxShadow: "var(--shadow-md)" }}
      >
        <div className="flex items-center justify-between px-6 py-4 shrink-0" style={{ borderBottom: "1px solid var(--border-light)" }}>
          <div>
            <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Facture — {invoice.reference || <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>sans référence</span>}
            </h2>
            <p className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>{invoice.vendor_name || "Fournisseur inconnu"}</p>
          </div>
          <button onClick={onClose} className="text-lg" style={{ color: "var(--text-tertiary)" }}>✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          <section>
            <h3 className="text-xs font-medium uppercase tracking-wide mb-3" style={{ color: "var(--text-tertiary)" }}>Données extraites par l&apos;IA</h3>
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
                <div key={label} className="rounded-lg px-3 py-2" style={{ background: "var(--bg-root)" }}>
                  <p className="text-xs mb-0.5" style={{ color: "var(--text-tertiary)" }}>{label}</p>
                  <p className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>{value || "—"}</p>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-xs font-medium uppercase tracking-wide mb-3" style={{ color: "var(--text-tertiary)" }}>Écriture comptable générée</h3>
            {loadingEntry ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-10 rounded-lg animate-pulse" style={{ background: "var(--bg-root)" }} />
                ))}
              </div>
            ) : !entry ? (
              <div className="rounded-xl px-4 py-6 text-center text-xs border-2 border-dashed" style={{ borderColor: "var(--border)", color: "var(--text-tertiary)" }}>
                {invoice.status === "processing" ? "Traitement en cours…" : "Aucune écriture générée."}
              </div>
            ) : (
              <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
                <div className="flex items-center justify-between px-4 py-2.5" style={{ background: "var(--bg-root)", borderBottom: "1px solid var(--border-light)" }}>
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-mono" style={{ color: "var(--text-secondary)" }}>{entry.reference || entry.id.slice(0, 8)}</span>
                    <span className="text-xs" style={{ color: "var(--text-tertiary)" }}>{entry.journal_code} · {fmtDate(entry.entry_date)}</span>
                  </div>
                  {entryCfg && (
                    <span className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium" style={{ color: entryCfg.color, background: entryCfg.bg, border: `1px solid ${entryCfg.border}` }}>
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: entryCfg.dot }} />
                      {STATUS_LABELS[entry.status] ?? entry.status}
                    </span>
                  )}
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-light)", color: "var(--text-tertiary)" }}>
                      <th className="px-4 py-2 text-left font-medium">Compte</th>
                      <th className="px-4 py-2 text-left font-medium">Libellé</th>
                      <th className="px-4 py-2 text-right font-medium">Débit</th>
                      <th className="px-4 py-2 text-right font-medium">Crédit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entry.lines.map((line) => (
                      <tr key={line.id} style={{ borderBottom: "1px solid var(--border-light)" }}>
                        <td className="px-4 py-2 font-mono" style={{ color: "var(--text-primary)" }}>{line.account_code}</td>
                        <td className="px-4 py-2 max-w-35 truncate" style={{ color: "var(--text-secondary)" }}>{line.account_label}</td>
                        <td className="px-4 py-2 text-right font-mono" style={{ color: "var(--text-primary)" }}>{parseFloat(line.debit) > 0 ? fmt(line.debit) : ""}</td>
                        <td className="px-4 py-2 text-right font-mono" style={{ color: "var(--text-primary)" }}>{parseFloat(line.credit) > 0 ? fmt(line.credit) : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {actionError && (
            <div className="rounded-xl px-4 py-3 text-sm" style={{ background: "var(--danger-bg)", border: "1px solid var(--danger-border)", color: "var(--danger)" }}>
              {actionError}
            </div>
          )}
        </div>

        {entry?.status === "draft" && (
          <div className="shrink-0 px-6 py-4 flex gap-3" style={{ borderTop: "1px solid var(--border-light)" }}>
            <button
              onClick={() => handleAction("cancel")}
              disabled={actionLoading !== null}
              className="flex-1 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40"
              style={{ border: "1px solid var(--danger-border)", color: "var(--danger)", background: "transparent" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--danger-bg)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              {actionLoading === "cancel" ? "Annulation…" : "Rejeter"}
            </button>
            <button
              onClick={() => handleAction("validate")}
              disabled={actionLoading !== null}
              className="flex-1 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 text-white"
              style={{ background: "var(--success)" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#047857")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "var(--success)")}
            >
              {actionLoading === "validate" ? "Validation…" : "Valider l'écriture"}
            </button>
          </div>
        )}
      </div>
    </>
  );
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function StatsBar({ invoices }: { invoices: Invoice[] }) {
  const counts = STATUSES.slice(1).map((s) => ({
    ...s,
    count: invoices.filter((i) => i.status === s.value).length,
  }));

  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
      {counts.map(({ value, label, count }) => {
        const cfg = STATUS_CONFIG[value] ?? STATUS_CONFIG.pending;
        return (
          <div key={value} className="rounded-xl px-4 py-3" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-1">
              <span className="h-2 w-2 rounded-full" style={{ background: cfg.dot }} />
              <span className="text-xs truncate" style={{ color: "var(--text-tertiary)" }}>{label}</span>
            </div>
            <p className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>{count}</p>
          </div>
        );
      })}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

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

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setPage(1); }, [search, status]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const inputStyle = { background: "var(--bg-card)", border: "1px solid var(--border)", color: "var(--text-primary)" };
  const inputFocus = (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
    e.target.style.border = "1px solid var(--amber-400)";
    e.target.style.boxShadow = "0 0 0 3px rgba(245,158,11,0.12)";
  };
  const inputBlur = (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
    e.target.style.border = "1px solid var(--border)";
    e.target.style.boxShadow = "none";
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>Factures</h1>
          <p className="mt-0.5 text-sm" style={{ color: "var(--text-secondary)" }}>
            {total > 0 ? `${total} facture${total > 1 ? "s" : ""}` : "Aucune facture"}
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-all"
          style={{ background: "var(--amber-600)", boxShadow: "var(--shadow-amber)" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--amber-700)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "var(--amber-600)")}
        >
          <Plus size={14} />
          Nouvelle facture
        </button>
      </div>

      {invoices.length > 0 && <StatsBar invoices={invoices} />}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          type="search"
          placeholder="Référence, fournisseur…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded-lg px-3 py-2 text-sm outline-none w-60"
          style={inputStyle}
          onFocus={inputFocus}
          onBlur={inputBlur}
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg px-3 py-2 text-sm outline-none"
          style={inputStyle}
          onFocus={inputFocus}
          onBlur={inputBlur}
        >
          {STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </div>

      {error && (
        <div className="rounded-xl px-4 py-3 text-sm" style={{ background: "var(--danger-bg)", border: "1px solid var(--danger-border)", color: "var(--danger)" }}>
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-14 rounded-xl animate-pulse" style={{ background: "var(--bg-card)" }} />
          ))}
        </div>
      ) : invoices.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed py-20 gap-3 text-center"
          style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
        >
          <div className="rounded-full p-4" style={{ background: "var(--bg-root)" }}>
            <Receipt size={24} style={{ color: "var(--text-tertiary)" }} />
          </div>
          <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>Aucune facture</p>
          <p className="text-xs max-w-xs" style={{ color: "var(--text-secondary)" }}>
            {search || status ? "Aucun résultat pour ces filtres." : "Créez votre première facture ou importez des documents via le module Documents."}
          </p>
          {!search && !status && (
            <button
              onClick={() => setShowModal(true)}
              className="mt-2 rounded-lg px-4 py-2 text-sm font-medium text-white"
              style={{ background: "var(--amber-600)" }}
            >
              + Nouvelle facture
            </button>
          )}
        </div>
      ) : (
        <div
          className="rounded-xl overflow-hidden"
          style={{ border: "1px solid var(--border)", background: "var(--bg-card)", boxShadow: "var(--shadow-sm)" }}
        >
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs" style={{ borderBottom: "1px solid var(--border-light)", color: "var(--text-tertiary)" }}>
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
            <tbody>
              {invoices.map((inv) => (
                <tr
                  key={inv.id}
                  onClick={() => setSelectedInvoice(inv)}
                  className="cursor-pointer transition-colors"
                  style={{ borderBottom: "1px solid var(--border-light)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-root)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: "var(--text-primary)" }}>
                    {inv.reference || <span style={{ color: "var(--text-tertiary)" }}>—</span>}
                  </td>
                  <td className="px-4 py-3 max-w-40 truncate" style={{ color: "var(--text-primary)" }}>
                    {inv.vendor_name || <span style={{ color: "var(--text-tertiary)" }}>—</span>}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs hidden sm:table-cell" style={{ color: "var(--text-secondary)" }}>
                    {inv.vendor_siren || "—"}
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
                    {fmtDate(inv.invoice_date)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs whitespace-nowrap" style={{ color: "var(--text-primary)" }}>
                    {fmt(inv.ht_amount)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs whitespace-nowrap hidden sm:table-cell" style={{ color: "var(--text-secondary)" }}>
                    {fmt(inv.tva_amount)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs font-medium whitespace-nowrap" style={{ color: "var(--text-primary)" }}>
                    {fmt(inv.ttc_amount)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={inv.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm" style={{ color: "var(--text-secondary)" }}>
          <span>Page {page} / {totalPages}</span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="rounded-lg px-3 py-1.5 text-xs transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ border: "1px solid var(--border)", color: "var(--text-primary)", background: "transparent" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-root)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              ← Précédent
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-lg px-3 py-1.5 text-xs transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ border: "1px solid var(--border)", color: "var(--text-primary)", background: "transparent" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-root)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              Suivant →
            </button>
          </div>
        </div>
      )}

      {showModal && <NewInvoiceModal onClose={() => setShowModal(false)} onCreated={load} />}
      <InvoiceDrawer invoice={selectedInvoice} onClose={() => setSelectedInvoice(null)} onActionDone={load} />
    </div>
  );
}
