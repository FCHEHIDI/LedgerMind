"use client";

import { useState, useCallback } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface MainCouranteLine {
  date: string;
  journal_code: string;
  reference: string;
  account_code: string;
  account_label: string;
  debit: string;
  credit: string;
  running_balance: string;
}

interface MainCouranteData {
  period: { from: string; to: string };
  journal_code: string | null;
  total_lines: number;
  total_debit: string;
  total_credit: string;
  lines: MainCouranteLine[];
}

interface GrandLivreLine {
  date: string;
  journal_code: string;
  reference: string;
  debit: string;
  credit: string;
}

interface GrandLivreAccount {
  account_code: string;
  account_label: string;
  total_debit: string;
  total_credit: string;
  solde: string;
  lines: GrandLivreLine[];
}

interface GrandLivreData {
  period: { from: string; to: string };
  account_prefix: string | null;
  total_accounts: number;
  accounts: GrandLivreAccount[];
}

interface BalanceAccount {
  account_code: string;
  account_label: string;
  total_debit: string;
  total_credit: string;
  solde_debiteur: string;
  solde_crediteur: string;
}

interface BalanceData {
  period: { from: string; to: string };
  is_balanced: boolean;
  total_debit: string;
  total_credit: string;
  accounts: BalanceAccount[];
}

type Tab = "main-courante" | "grand-livre" | "balance";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(value: string | null | undefined): string {
  if (!value) return "—";
  const num = parseFloat(value);
  if (isNaN(num) || num === 0) return "—";
  return new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
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

// ── Shared components ─────────────────────────────────────────────────────────

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

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/50 px-4 py-3">
      <p className="text-xs text-zinc-400 uppercase tracking-wide mb-0.5">{label}</p>
      <p className="text-base font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">{value}</p>
    </div>
  );
}

function CsvButton({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      download
      className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-600 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
    >
      ↓ {label}
    </a>
  );
}

// ── Filter bar ────────────────────────────────────────────────────────────────

interface FilterBarProps {
  from: string;
  to: string;
  onFromChange: (v: string) => void;
  onToChange: (v: string) => void;
  extraField?: React.ReactNode;
  onSubmit: () => void;
  loading: boolean;
}

function FilterBar({ from, to, onFromChange, onToChange, extraField, onSubmit, loading }: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <label className="block text-xs font-medium text-zinc-500 mb-1">Du</label>
        <input
          type="date"
          value={from}
          onChange={(e) => onFromChange(e.target.value)}
          className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-zinc-500 mb-1">Au</label>
        <input
          type="date"
          value={to}
          onChange={(e) => onToChange(e.target.value)}
          className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
        />
      </div>
      {extraField}
      <button
        onClick={onSubmit}
        disabled={loading}
        className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
      >
        {loading ? "Chargement…" : "Calculer"}
      </button>
    </div>
  );
}

// ── Tab: Main courante ────────────────────────────────────────────────────────

function MainCouranteTab() {
  const year = currentYear();
  const [from, setFrom] = useState(isoDate(year, 1, 1));
  const [to, setTo] = useState(isoDate(year, 12, 31));
  const [journalCode, setJournalCode] = useState("");
  const [data, setData] = useState<MainCouranteData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const params = new URLSearchParams({ from, to });
      if (journalCode) params.set("journal_code", journalCode.toUpperCase());
      const res = await fetch(`/api/journal/export/main-courante?${params}`);
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? d.error ?? `Erreur ${res.status}`);
      setData(d);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, [from, to, journalCode]);

  const csvParams = new URLSearchParams({ from, to, format: "csv" });
  if (journalCode) csvParams.set("journal_code", journalCode.toUpperCase());

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5 shadow-sm">
        <FilterBar
          from={from} to={to}
          onFromChange={setFrom} onToChange={setTo}
          loading={loading} onSubmit={load}
          extraField={
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Journal (optionnel)</label>
              <input
                type="text"
                value={journalCode}
                onChange={(e) => setJournalCode(e.target.value)}
                placeholder="BQ, ACH, VTE…"
                className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm w-32 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              />
            </div>
          }
        />
      </div>

      {error && <ErrorMsg msg={error} />}
      {loading && <LoadingSpinner />}

      {data && !loading && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <SummaryCard label="Lignes" value={String(data.total_lines)} />
            <SummaryCard label="Total débit" value={`${fmt(data.total_debit)} €`} />
            <SummaryCard label="Total crédit" value={`${fmt(data.total_credit)} €`} />
            <div className="flex items-end">
              <CsvButton href={`/api/journal/export/main-courante?${csvParams}`} label="Exporter CSV" />
            </div>
          </div>

          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
            {data.lines.length === 0 ? (
              <p className="text-sm text-zinc-400 text-center py-10">Aucune écriture sur cette période.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-100 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/50">
                      {["Date", "Journal", "Référence", "Compte", "Libellé", "Débit", "Crédit", "Solde cumulatif"].map((h) => (
                        <th key={h} className={`px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase ${h.startsWith("D") || h.startsWith("C") || h.startsWith("S") && h !== "Compte" ? "text-right" : "text-left"}`}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                    {data.lines.map((line, i) => (
                      <tr key={i} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/20">
                        <td className="px-4 py-2 whitespace-nowrap text-zinc-500">{fmtDate(line.date)}</td>
                        <td className="px-4 py-2 font-mono text-xs text-zinc-400">{line.journal_code}</td>
                        <td className="px-4 py-2 font-mono text-xs text-zinc-600 dark:text-zinc-400">{line.reference || "—"}</td>
                        <td className="px-4 py-2 font-mono text-xs text-zinc-500">{line.account_code}</td>
                        <td className="px-4 py-2 text-zinc-700 dark:text-zinc-300 max-w-[180px] truncate">{line.account_label || "—"}</td>
                        <td className="px-4 py-2 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(line.debit)}</td>
                        <td className="px-4 py-2 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(line.credit)}</td>
                        <td className={`px-4 py-2 text-right tabular-nums font-medium ${parseFloat(line.running_balance) < 0 ? "text-red-500" : "text-zinc-800 dark:text-zinc-200"}`}>
                          {fmt(line.running_balance)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Tab: Grand livre ──────────────────────────────────────────────────────────

function GrandLivreTab() {
  const year = currentYear();
  const [from, setFrom] = useState(isoDate(year, 1, 1));
  const [to, setTo] = useState(isoDate(year, 12, 31));
  const [accountPrefix, setAccountPrefix] = useState("");
  const [data, setData] = useState<GrandLivreData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    setExpanded(new Set());
    try {
      const params = new URLSearchParams({ from, to });
      if (accountPrefix) params.set("account_prefix", accountPrefix);
      const res = await fetch(`/api/journal/export/grand-livre?${params}`);
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? d.error ?? `Erreur ${res.status}`);
      setData(d);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, [from, to, accountPrefix]);

  function toggleAccount(code: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  function expandAll() {
    if (!data) return;
    setExpanded(new Set(data.accounts.map((a) => a.account_code)));
  }

  function collapseAll() {
    setExpanded(new Set());
  }

  const csvParams = new URLSearchParams({ from, to, format: "csv" });
  if (accountPrefix) csvParams.set("account_prefix", accountPrefix);

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5 shadow-sm">
        <FilterBar
          from={from} to={to}
          onFromChange={setFrom} onToChange={setTo}
          loading={loading} onSubmit={load}
          extraField={
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Préfixe compte</label>
              <input
                type="text"
                value={accountPrefix}
                onChange={(e) => setAccountPrefix(e.target.value)}
                placeholder="4, 6, 512…"
                className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm w-28 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              />
            </div>
          }
        />
      </div>

      {error && <ErrorMsg msg={error} />}
      {loading && <LoadingSpinner />}

      {data && !loading && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-zinc-500">
              <span className="font-semibold text-zinc-800 dark:text-zinc-200">{data.total_accounts}</span> compte(s)
            </p>
            <div className="flex items-center gap-3">
              <button onClick={expandAll} className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300">Tout déplier</button>
              <button onClick={collapseAll} className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300">Tout replier</button>
              <CsvButton href={`/api/journal/export/grand-livre?${csvParams}`} label="Exporter CSV" />
            </div>
          </div>

          {data.accounts.length === 0 ? (
            <p className="text-sm text-zinc-400 text-center py-10">Aucun compte sur cette période.</p>
          ) : (
            <div className="space-y-2">
              {data.accounts.map((acc) => {
                const isExpanded = expanded.has(acc.account_code);
                const solde = parseFloat(acc.solde);
                return (
                  <div key={acc.account_code} className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
                    <div
                      className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/30"
                      onClick={() => toggleAccount(acc.account_code)}
                    >
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-sm font-semibold text-zinc-900 dark:text-zinc-50">{acc.account_code}</span>
                        <span className="text-sm text-zinc-600 dark:text-zinc-400">{acc.account_label || "—"}</span>
                        <span className="text-xs text-zinc-400">{acc.lines.length} ligne(s)</span>
                      </div>
                      <div className="flex items-center gap-4 text-xs">
                        <span className="tabular-nums text-zinc-500">D: {fmt(acc.total_debit)}</span>
                        <span className="tabular-nums text-zinc-500">C: {fmt(acc.total_credit)}</span>
                        <span className={`tabular-nums font-semibold ${solde > 0 ? "text-zinc-800 dark:text-zinc-200" : solde < 0 ? "text-red-500" : "text-zinc-400"}`}>
                          Solde: {fmt(acc.solde)}
                        </span>
                        <span className="text-zinc-300 dark:text-zinc-600">{isExpanded ? "▲" : "▼"}</span>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="border-t border-zinc-100 dark:border-zinc-800">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="bg-zinc-50 dark:bg-zinc-800/50">
                              {["Date", "Journal", "Référence", "Débit", "Crédit"].map((h) => (
                                <th key={h} className={`px-4 py-2 text-xs font-medium text-zinc-400 uppercase ${h === "Débit" || h === "Crédit" ? "text-right" : "text-left"}`}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                            {acc.lines.map((line, i) => (
                              <tr key={i} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/20">
                                <td className="px-4 py-2 whitespace-nowrap text-zinc-500">{fmtDate(line.date)}</td>
                                <td className="px-4 py-2 font-mono text-xs text-zinc-400">{line.journal_code}</td>
                                <td className="px-4 py-2 font-mono text-xs text-zinc-600 dark:text-zinc-400">{line.reference || "—"}</td>
                                <td className="px-4 py-2 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(line.debit)}</td>
                                <td className="px-4 py-2 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(line.credit)}</td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot>
                            <tr className="border-t border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/50">
                              <td colSpan={3} className="px-4 py-2 text-xs font-semibold text-zinc-500">Total</td>
                              <td className="px-4 py-2 text-right font-semibold tabular-nums text-zinc-800 dark:text-zinc-200">{fmt(acc.total_debit)}</td>
                              <td className="px-4 py-2 text-right font-semibold tabular-nums text-zinc-800 dark:text-zinc-200">{fmt(acc.total_credit)}</td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Tab: Balance ──────────────────────────────────────────────────────────────

function BalanceTab() {
  const year = currentYear();
  const [from, setFrom] = useState(isoDate(year, 1, 1));
  const [to, setTo] = useState(isoDate(year, 12, 31));
  const [accountPrefix, setAccountPrefix] = useState("");
  const [data, setData] = useState<BalanceData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const params = new URLSearchParams({ from, to });
      if (accountPrefix) params.set("account_prefix", accountPrefix);
      const res = await fetch(`/api/journal/export/balance?${params}`);
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? d.error ?? `Erreur ${res.status}`);
      setData(d);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, [from, to, accountPrefix]);

  const csvParams = new URLSearchParams({ from, to, format: "csv" });
  if (accountPrefix) csvParams.set("account_prefix", accountPrefix);

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5 shadow-sm">
        <FilterBar
          from={from} to={to}
          onFromChange={setFrom} onToChange={setTo}
          loading={loading} onSubmit={load}
          extraField={
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Préfixe compte</label>
              <input
                type="text"
                value={accountPrefix}
                onChange={(e) => setAccountPrefix(e.target.value)}
                placeholder="4, 6, 7…"
                className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm w-28 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              />
            </div>
          }
        />
      </div>

      {error && <ErrorMsg msg={error} />}
      {loading && <LoadingSpinner />}

      {data && !loading && (
        <>
          {!data.is_balanced && (
            <div className="rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-900/20 p-3 text-sm text-amber-700 dark:text-amber-400">
              ⚠ La balance n&apos;est pas équilibrée — vérifier les écritures.
            </div>
          )}

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <SummaryCard label="Comptes" value={String(data.accounts.length)} />
            <SummaryCard label="Total débit" value={`${fmt(data.total_debit)} €`} />
            <SummaryCard label="Total crédit" value={`${fmt(data.total_credit)} €`} />
            <div className="flex items-end gap-3">
              {data.is_balanced ? (
                <span className="text-sm text-emerald-600 dark:text-emerald-400 font-medium">✓ Équilibrée</span>
              ) : (
                <span className="text-sm text-red-500 font-medium">✗ Déséquilibrée</span>
              )}
              <CsvButton href={`/api/journal/export/balance?${csvParams}`} label="CSV" />
            </div>
          </div>

          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
            {data.accounts.length === 0 ? (
              <p className="text-sm text-zinc-400 text-center py-10">Aucun compte sur cette période.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-100 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/50">
                      <th className="text-left px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Compte</th>
                      <th className="text-left px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Libellé</th>
                      <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Débit</th>
                      <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Crédit</th>
                      <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Solde débiteur</th>
                      <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Solde créditeur</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                    {data.accounts.map((acc) => (
                      <tr key={acc.account_code} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/20">
                        <td className="px-4 py-2 font-mono text-xs text-zinc-500">{acc.account_code}</td>
                        <td className="px-4 py-2 text-zinc-700 dark:text-zinc-300">{acc.account_label || "—"}</td>
                        <td className="px-4 py-2 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(acc.total_debit)}</td>
                        <td className="px-4 py-2 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(acc.total_credit)}</td>
                        <td className="px-4 py-2 text-right tabular-nums font-medium text-zinc-800 dark:text-zinc-200">{fmt(acc.solde_debiteur)}</td>
                        <td className="px-4 py-2 text-right tabular-nums font-medium text-zinc-800 dark:text-zinc-200">{fmt(acc.solde_crediteur)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/50">
                      <td colSpan={2} className="px-4 py-2.5 text-xs font-bold text-zinc-600 dark:text-zinc-400 uppercase">Total général</td>
                      <td className="px-4 py-2.5 text-right font-bold tabular-nums text-zinc-900 dark:text-zinc-50">{fmt(data.total_debit)}</td>
                      <td className="px-4 py-2.5 text-right font-bold tabular-nums text-zinc-900 dark:text-zinc-50">{fmt(data.total_credit)}</td>
                      <td colSpan={2} />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string; description: string }[] = [
  { id: "main-courante", label: "Main courante", description: "Journal chronologique avec solde cumulatif" },
  { id: "grand-livre", label: "Grand livre", description: "Écritures détaillées regroupées par compte" },
  { id: "balance", label: "Balance", description: "Synthèse débit/crédit/solde par compte" },
];

export default function ExportsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("balance");

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Exports comptables</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Main courante, Grand livre et Balance de vérification
        </p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-zinc-200 dark:border-zinc-800 gap-1">
        {TABS.map(({ id, label, description }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            title={description}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === id
                ? "border-zinc-900 dark:border-zinc-100 text-zinc-900 dark:text-zinc-50"
                : "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "main-courante" && <MainCouranteTab />}
      {activeTab === "grand-livre" && <GrandLivreTab />}
      {activeTab === "balance" && <BalanceTab />}
    </div>
  );
}
