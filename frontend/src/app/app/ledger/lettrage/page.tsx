"use client";

import { useState, useCallback } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface OpenItem {
  id: string;
  account_code: string;
  account_label: string;
  debit: string;
  credit: string;
  date: string;
  reference: string;
  journal_code: string;
  journal_entry_id: string;
}

interface LetteringLine {
  id: string;
  account_entry_id: string;
  account_code: string;
  account_label: string;
  debit: string;
  credit: string;
  entry_date: string;
  reference: string;
  journal_code: string;
}

interface Lettering {
  id: string;
  letter_code: string;
  account_code: string;
  is_balanced: boolean;
  created_at: string;
  total_debit: string;
  total_credit: string;
  lines: LetteringLine[];
}

interface OpenItemsResponse {
  period: { from: string; to: string };
  account_code: string | null;
  total_open_items: number;
  entries: OpenItem[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(value: string | null | undefined): string {
  if (!value) return "—";
  const num = parseFloat(value);
  if (isNaN(num) || num === 0) return "—";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(num);
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR");
}

function currentYear(): number {
  return new Date().getFullYear();
}

function isoDate(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-10">
      <div className="h-5 w-5 rounded-full border-2 border-zinc-300 border-t-zinc-600 animate-spin" />
    </div>
  );
}

function ErrorMsg({ msg }: { msg: string }) {
  return (
    <div className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-600 dark:text-red-400">
      {msg}
    </div>
  );
}

// ── LettrageList ──────────────────────────────────────────────────────────────

function LettrageList({
  lettrages,
  loading,
  onDelete,
}: {
  lettrages: Lettering[];
  loading: boolean;
  onDelete: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await onDelete(id);
    } finally {
      setDeletingId(null);
    }
  }

  if (loading) return <LoadingSpinner />;
  if (lettrages.length === 0) return (
    <p className="text-sm text-zinc-400 text-center py-8">Aucun lettrage existant.</p>
  );

  return (
    <div className="space-y-2">
      {lettrages.map((l) => (
        <div key={l.id} className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
          <div
            className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/30"
            onClick={() => setExpanded(expanded === l.id ? null : l.id)}
          >
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm font-bold text-zinc-900 dark:text-zinc-50">{l.letter_code}</span>
              <span className="font-mono text-xs text-zinc-400">{l.account_code}</span>
              {l.is_balanced ? (
                <span className="rounded-full px-2 py-0.5 text-xs bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">Équilibré</span>
              ) : (
                <span className="rounded-full px-2 py-0.5 text-xs bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">Déséquilibré</span>
              )}
              <span className="text-xs text-zinc-400">{l.lines.length} ligne(s)</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-zinc-400">{fmtDate(l.created_at)}</span>
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(l.id); }}
                disabled={deletingId === l.id}
                className="text-xs text-red-400 hover:text-red-600 disabled:opacity-50 px-2 py-0.5 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
              >
                {deletingId === l.id ? "…" : "Délettrer"}
              </button>
              <span className="text-xs text-zinc-300 dark:text-zinc-600">{expanded === l.id ? "▲" : "▼"}</span>
            </div>
          </div>

          {expanded === l.id && (
            <div className="border-t border-zinc-100 dark:border-zinc-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-zinc-50 dark:bg-zinc-800/50">
                    <th className="text-left px-4 py-2 text-xs font-medium text-zinc-400 uppercase">Compte</th>
                    <th className="text-left px-4 py-2 text-xs font-medium text-zinc-400 uppercase">Date</th>
                    <th className="text-left px-4 py-2 text-xs font-medium text-zinc-400 uppercase">Référence</th>
                    <th className="text-left px-4 py-2 text-xs font-medium text-zinc-400 uppercase">Journal</th>
                    <th className="text-right px-4 py-2 text-xs font-medium text-zinc-400 uppercase">Débit</th>
                    <th className="text-right px-4 py-2 text-xs font-medium text-zinc-400 uppercase">Crédit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                  {l.lines.map((line) => (
                    <tr key={line.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/20">
                      <td className="px-4 py-2">
                        <span className="font-mono text-xs text-zinc-400">{line.account_code}</span>
                        {line.account_label && <span className="ml-1.5 text-xs text-zinc-500">{line.account_label}</span>}
                      </td>
                      <td className="px-4 py-2 text-zinc-500 text-xs">{fmtDate(line.entry_date)}</td>
                      <td className="px-4 py-2 font-mono text-xs text-zinc-600 dark:text-zinc-400">{line.reference || "—"}</td>
                      <td className="px-4 py-2 font-mono text-xs text-zinc-400">{line.journal_code}</td>
                      <td className="px-4 py-2 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(line.debit)}</td>
                      <td className="px-4 py-2 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(line.credit)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/50">
                    <td colSpan={4} className="px-4 py-2 text-xs font-semibold text-zinc-500">Total</td>
                    <td className="px-4 py-2 text-right font-semibold tabular-nums text-zinc-800 dark:text-zinc-200">{fmt(l.total_debit)}</td>
                    <td className="px-4 py-2 text-right font-semibold tabular-nums text-zinc-800 dark:text-zinc-200">{fmt(l.total_credit)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function LetteragePage() {
  const year = currentYear();
  const [accountCode, setAccountCode] = useState("401");
  const [from, setFrom] = useState(isoDate(year, 1, 1));
  const [to, setTo] = useState(isoDate(year, 12, 31));

  const [openItems, setOpenItems] = useState<OpenItem[] | null>(null);
  const [loadingItems, setLoadingItems] = useState(false);
  const [itemsError, setItemsError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Set<string>>(new Set());

  const [lettrages, setLettrages] = useState<Lettering[]>([]);
  const [loadingLettrages, setLoadingLettrages] = useState(false);

  const [busyLetter, setBusyLetter] = useState(false);
  const [letterError, setLetterError] = useState<string | null>(null);
  const [letterSuccess, setLetterSuccess] = useState<string | null>(null);

  // Load existing lettrages
  const loadLettrages = useCallback(async () => {
    setLoadingLettrages(true);
    try {
      const res = await fetch("/api/lettrage");
      const d = await res.json();
      setLettrages(Array.isArray(d) ? d : d.results ?? []);
    } catch {
      // silent — lettrages are supplementary info
    } finally {
      setLoadingLettrages(false);
    }
  }, []);

  // Load on mount
  useState(() => { loadLettrages(); });

  // Fetch open items
  const loadOpenItems = useCallback(async () => {
    setLoadingItems(true);
    setItemsError(null);
    setOpenItems(null);
    setSelected(new Set());
    try {
      const params = new URLSearchParams({ from, to });
      if (accountCode) params.set("account_code", accountCode);
      const res = await fetch(`/api/lettrage/open-items?${params.toString()}`);
      const d: OpenItemsResponse = await res.json();
      if (!res.ok) throw new Error((d as unknown as { error: string }).error ?? "Erreur");
      setOpenItems(d.entries);
    } catch (e: unknown) {
      setItemsError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoadingItems(false);
    }
  }, [accountCode, from, to]);

  // Toggle selection
  function toggleRow(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (!openItems) return;
    if (selected.size === openItems.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(openItems.map((e) => e.id)));
    }
  }

  // Calculate balance of selection
  const selectedItems = openItems?.filter((e) => selected.has(e.id)) ?? [];
  const totalDebit = selectedItems.reduce((sum, e) => sum + parseFloat(e.debit || "0"), 0);
  const totalCredit = selectedItems.reduce((sum, e) => sum + parseFloat(e.credit || "0"), 0);
  const isBalanced = Math.abs(totalDebit - totalCredit) < 0.01;

  // Create lettrage
  async function handleLetter() {
    if (selected.size < 2) return;
    setBusyLetter(true);
    setLetterError(null);
    setLetterSuccess(null);
    try {
      const res = await fetch("/api/lettrage", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_entry_ids: Array.from(selected) }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? d.error ?? `Erreur ${res.status}`);
      setLetterSuccess(`Lettrage "${d.letter_code}" créé avec succès.`);
      setSelected(new Set());
      // Remove lettered items from open items list
      setOpenItems((prev) => prev?.filter((e) => !selected.has(e.id)) ?? null);
      // Refresh lettrages list
      await loadLettrages();
    } catch (e: unknown) {
      setLetterError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setBusyLetter(false);
    }
  }

  // Delete lettrage
  async function handleDelete(id: string) {
    const res = await fetch(`/api/lettrage/${id}`, { method: "DELETE" });
    if (res.ok || res.status === 204) {
      setLettrages((prev) => prev.filter((l) => l.id !== id));
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Lettrage</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Pointage des comptes fournisseurs (401) et clients (411)
        </p>
      </div>

      {/* Filter bar */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 mb-4">
          Postes ouverts
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Compte</label>
            <select
              value={accountCode}
              onChange={(e) => setAccountCode(e.target.value)}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            >
              <option value="">Tous (401 + 411)</option>
              <option value="401">401 — Fournisseurs</option>
              <option value="411">411 — Clients</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Du</label>
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Au</label>
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            />
          </div>
          <button
            onClick={loadOpenItems}
            disabled={loadingItems}
            className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
          >
            {loadingItems ? "Chargement…" : "Charger les postes"}
          </button>
        </div>
      </div>

      {itemsError && <ErrorMsg msg={itemsError} />}
      {loadingItems && <LoadingSpinner />}

      {openItems !== null && !loadingItems && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
          {/* Selection bar */}
          {selected.size > 0 && (
            <div className="flex items-center justify-between px-4 py-2.5 bg-zinc-50 dark:bg-zinc-800/50 border-b border-zinc-100 dark:border-zinc-800">
              <div className="text-sm text-zinc-600 dark:text-zinc-400">
                <span className="font-medium">{selected.size}</span> sélectionné(s) —{" "}
                Débit: <span className="tabular-nums font-medium">{new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(totalDebit)}</span>{" "}
                Crédit: <span className="tabular-nums font-medium">{new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(totalCredit)}</span>{" "}
                {isBalanced ? (
                  <span className="text-emerald-600 dark:text-emerald-400 font-medium ml-1">✓ Équilibré</span>
                ) : (
                  <span className="text-amber-600 dark:text-amber-400 font-medium ml-1">
                    Écart: {new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(Math.abs(totalDebit - totalCredit))}
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                {letterError && <span className="text-xs text-red-500">{letterError}</span>}
                {letterSuccess && <span className="text-xs text-emerald-600">{letterSuccess}</span>}
                <button
                  onClick={handleLetter}
                  disabled={busyLetter || selected.size < 2}
                  title={selected.size < 2 ? "Sélectionnez au moins 2 lignes" : undefined}
                  className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-3 py-1.5 text-xs font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
                >
                  {busyLetter ? "Traitement…" : "Lettrer la sélection"}
                </button>
              </div>
            </div>
          )}

          {openItems.length === 0 ? (
            <p className="text-sm text-zinc-400 text-center py-10">
              Aucun poste ouvert sur cette période.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-100 dark:border-zinc-800">
                    <th className="px-4 py-2.5">
                      <input
                        type="checkbox"
                        checked={openItems.length > 0 && selected.size === openItems.length}
                        onChange={toggleAll}
                        className="rounded border-zinc-300 dark:border-zinc-600"
                      />
                    </th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Compte</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Date</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Référence</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Journal</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Débit</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Crédit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                  {openItems.map((item) => {
                    const isSelected = selected.has(item.id);
                    return (
                      <tr
                        key={item.id}
                        onClick={() => toggleRow(item.id)}
                        className={`cursor-pointer ${isSelected ? "bg-blue-50 dark:bg-blue-900/20" : "hover:bg-zinc-50 dark:hover:bg-zinc-800/30"}`}
                      >
                        <td className="px-4 py-2.5" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleRow(item.id)}
                            className="rounded border-zinc-300 dark:border-zinc-600"
                          />
                        </td>
                        <td className="px-4 py-2.5">
                          <span className="font-mono text-xs text-zinc-500">{item.account_code}</span>
                          {item.account_label && (
                            <span className="ml-1.5 text-xs text-zinc-600 dark:text-zinc-400">{item.account_label}</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-zinc-500 whitespace-nowrap">{fmtDate(item.date)}</td>
                        <td className="px-4 py-2.5 font-mono text-xs text-zinc-600 dark:text-zinc-400">{item.reference || "—"}</td>
                        <td className="px-4 py-2.5 font-mono text-xs text-zinc-400">{item.journal_code}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(item.debit)}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(item.credit)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Existing lettrages */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
            Lettrages existants
          </h2>
          <button
            onClick={loadLettrages}
            disabled={loadingLettrages}
            className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 disabled:opacity-50"
          >
            Actualiser
          </button>
        </div>
        <LettrageList
          lettrages={lettrages}
          loading={loadingLettrages}
          onDelete={handleDelete}
        />
      </div>
    </div>
  );
}
