"use client";

import { useState, useCallback, useRef } from "react";

// ── Types ────────────────────────────────────────────────────────────────────

type MatchStatus = "unmatched" | "matched" | "manual" | "ignored";
type StatementStatus = "pending" | "in_progress" | "reconciled";

interface BankStatementLine {
  id: string;
  transaction_date: string;
  value_date: string | null;
  label: string;
  amount: string;
  match_status: MatchStatus;
  matched_entry_id: string | null;
  matched_account_code: string | null;
  matched_reference: string | null;
  matched_at: string | null;
}

interface BankStatement {
  id: string;
  account_code: string;
  account_label: string;
  period_from: string;
  period_to: string;
  opening_balance: string;
  closing_balance: string;
  status: StatementStatus;
  created_at: string;
  lines_count: number;
  matched_count: number;
  unmatched_count: number;
  lines: BankStatementLine[];
}

interface UnmatchedEntry {
  id: string;
  account_code: string;
  date: string;
  reference: string;
  debit: string;
  credit: string;
}

interface ReconciliationReport {
  statement_id: string;
  account_code: string;
  account_label: string;
  period: { from: string; to: string };
  opening_balance: string;
  closing_balance: string;
  sum_matched_bank: string;
  sum_matched_accounting: string;
  is_balanced: boolean;
  statement_status: string;
  unmatched_bank_lines: { id: string; transaction_date: string; label: string; amount: string }[];
  unmatched_accounting_entries: UnmatchedEntry[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(value: string | null | undefined): string {
  if (!value) return "—";
  const num = parseFloat(value);
  if (isNaN(num)) return "—";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(num);
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR");
}

const STATUS_LABELS: Record<StatementStatus, string> = {
  pending: "En attente",
  in_progress: "En cours",
  reconciled: "Rapproché",
};

const STATUS_COLORS: Record<StatementStatus, string> = {
  pending: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  in_progress: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  reconciled: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
};

const MATCH_LABELS: Record<MatchStatus, string> = {
  unmatched: "Non rapproché",
  matched: "Rapproché (auto)",
  manual: "Rapproché (manuel)",
  ignored: "Ignoré",
};

const MATCH_COLORS: Record<MatchStatus, string> = {
  unmatched: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  matched: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  manual: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  ignored: "bg-zinc-100 text-zinc-400 dark:bg-zinc-800/50 dark:text-zinc-500",
};

// ── Sub-components ────────────────────────────────────────────────────────────

function Badge({ status }: { status: MatchStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${MATCH_COLORS[status]}`}>
      {MATCH_LABELS[status]}
    </span>
  );
}

function StatBadge({ status }: { status: StatementStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="h-6 w-6 rounded-full border-2 border-zinc-300 border-t-zinc-600 animate-spin" />
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

// ── Manual match modal ────────────────────────────────────────────────────────

function ManualMatchModal({
  line,
  statementId,
  entries,
  onClose,
  onMatched,
}: {
  line: BankStatementLine;
  statementId: string;
  entries: UnmatchedEntry[];
  onClose: () => void;
  onMatched: (updatedLine: BankStatementLine) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function doMatch(entryId: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bank-statements/${statementId}/match-line`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ line_id: line.id, account_entry_id: entryId }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail ?? d.error ?? `Erreur ${res.status}`);
      }
      const updated: BankStatementLine = await res.json();
      onMatched(updated);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl rounded-2xl bg-white dark:bg-zinc-900 shadow-2xl border border-zinc-200 dark:border-zinc-700 overflow-hidden">
        <div className="flex items-start justify-between px-6 py-4 border-b border-zinc-100 dark:border-zinc-800">
          <div>
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Rapprochement manuel</h2>
            <p className="text-xs text-zinc-400 mt-0.5">
              {fmtDate(line.transaction_date)} · {line.label} · <span className="font-medium">{fmt(line.amount)}</span>
            </p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 text-lg leading-none">×</button>
        </div>

        <div className="p-6 max-h-96 overflow-y-auto">
          {error && <ErrorMsg msg={error} />}
          {entries.length === 0 ? (
            <p className="text-sm text-zinc-400 text-center py-6">
              Aucune écriture comptable non rapprochée disponible sur cette période.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-100 dark:border-zinc-800">
                  <th className="text-left py-2 text-xs font-medium text-zinc-400 uppercase">Date</th>
                  <th className="text-left py-2 text-xs font-medium text-zinc-400 uppercase">Référence</th>
                  <th className="text-left py-2 text-xs font-medium text-zinc-400 uppercase">Compte</th>
                  <th className="text-right py-2 text-xs font-medium text-zinc-400 uppercase">Débit</th>
                  <th className="text-right py-2 text-xs font-medium text-zinc-400 uppercase">Crédit</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                {entries.map((e) => (
                  <tr key={e.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/30">
                    <td className="py-2 text-zinc-500">{fmtDate(e.date)}</td>
                    <td className="py-2 font-mono text-xs text-zinc-600 dark:text-zinc-400">{e.reference || "—"}</td>
                    <td className="py-2 font-mono text-xs text-zinc-400">{e.account_code}</td>
                    <td className="py-2 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(e.debit)}</td>
                    <td className="py-2 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(e.credit)}</td>
                    <td className="py-2 text-right">
                      <button
                        disabled={busy}
                        onClick={() => doMatch(e.id)}
                        className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-3 py-1 text-xs font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
                      >
                        Choisir
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Statement detail view ─────────────────────────────────────────────────────

function StatementDetail({
  statement: initial,
  onBack,
}: {
  statement: BankStatement;
  onBack: () => void;
}) {
  const [statement, setStatement] = useState<BankStatement>(initial);
  const [autoMatchResult, setAutoMatchResult] = useState<{ matched: number; unmatched: number } | null>(null);
  const [busyAutoMatch, setBusyAutoMatch] = useState(false);
  const [busyLine, setBusyLine] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [matchModal, setMatchModal] = useState<{ line: BankStatementLine; entries: UnmatchedEntry[] } | null>(null);
  const [report, setReport] = useState<ReconciliationReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);

  async function refreshStatement() {
    const res = await fetch(`/api/bank-statements/${statement.id}`);
    if (res.ok) setStatement(await res.json());
  }

  async function handleAutoMatch() {
    setBusyAutoMatch(true);
    setError(null);
    setAutoMatchResult(null);
    try {
      const res = await fetch(`/api/bank-statements/${statement.id}/auto-match`, {
        method: "POST",
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? d.error ?? `Erreur ${res.status}`);
      setAutoMatchResult({ matched: d.matched, unmatched: d.unmatched });
      await refreshStatement();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setBusyAutoMatch(false);
    }
  }

  async function handleUnmatch(line: BankStatementLine) {
    setBusyLine(line.id);
    setError(null);
    try {
      const res = await fetch(`/api/bank-statements/${statement.id}/unmatch-line`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ line_id: line.id }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? d.error ?? `Erreur ${res.status}`);
      setStatement((s) => ({
        ...s,
        lines: s.lines.map((l) => (l.id === line.id ? d : l)),
      }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setBusyLine(null);
    }
  }

  async function handleIgnore(line: BankStatementLine) {
    setBusyLine(line.id);
    setError(null);
    try {
      const res = await fetch(`/api/bank-statements/${statement.id}/ignore-line`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ line_id: line.id }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? d.error ?? `Erreur ${res.status}`);
      setStatement((s) => ({
        ...s,
        lines: s.lines.map((l) => (l.id === line.id ? d : l)),
      }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setBusyLine(null);
    }
  }

  async function handleOpenManualMatch(line: BankStatementLine) {
    setError(null);
    try {
      const res = await fetch(`/api/bank-statements/${statement.id}/report`);
      const reportData: ReconciliationReport = await res.json();
      setMatchModal({ line, entries: reportData.unmatched_accounting_entries });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Impossible de charger les écritures.");
    }
  }

  function handleMatched(updatedLine: BankStatementLine) {
    setStatement((s) => ({
      ...s,
      lines: s.lines.map((l) => (l.id === updatedLine.id ? updatedLine : l)),
    }));
    setMatchModal(null);
  }

  async function loadReport() {
    setLoadingReport(true);
    try {
      const res = await fetch(`/api/bank-statements/${statement.id}/report`);
      const d = await res.json();
      if (!res.ok) throw new Error(d.error ?? "Erreur rapport");
      setReport(d);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur rapport");
    } finally {
      setLoadingReport(false);
    }
  }

  const matched = statement.lines.filter(
    (l) => l.match_status === "matched" || l.match_status === "manual"
  ).length;
  const total = statement.lines.length;
  const pct = total > 0 ? Math.round((matched / total) * 100) : 0;

  return (
    <>
      {matchModal && (
        <ManualMatchModal
          line={matchModal.line}
          statementId={statement.id}
          entries={matchModal.entries}
          onClose={() => setMatchModal(null)}
          onMatched={handleMatched}
        />
      )}

      <div className="space-y-4">
        {/* Back + header */}
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
          >
            ← Retour
          </button>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">
            {statement.account_code}
            {statement.account_label ? ` — ${statement.account_label}` : ""}
          </h2>
          <StatBadge status={statement.status} />
        </div>

        {/* Stats bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Période", value: `${fmtDate(statement.period_from)} → ${fmtDate(statement.period_to)}` },
            { label: "Solde ouverture", value: fmt(statement.opening_balance) },
            { label: "Solde clôture", value: fmt(statement.closing_balance) },
            { label: "Progression", value: `${matched}/${total} (${pct}%)` },
          ].map((s) => (
            <div key={s.label} className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-4 py-3">
              <p className="text-xs text-zinc-400">{s.label}</p>
              <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 mt-0.5">{s.value}</p>
            </div>
          ))}
        </div>

        {/* Progress bar */}
        <div className="h-2 w-full rounded-full bg-zinc-100 dark:bg-zinc-800">
          <div
            className="h-2 rounded-full bg-emerald-500 transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>

        {error && <ErrorMsg msg={error} />}
        {autoMatchResult && (
          <div className="rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20 p-3 text-sm text-emerald-700 dark:text-emerald-400">
            Auto-match terminé: {autoMatchResult.matched} rapproché(s), {autoMatchResult.unmatched} non rapproché(s).
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={handleAutoMatch}
            disabled={busyAutoMatch}
            className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
          >
            {busyAutoMatch ? "Traitement…" : "Auto-rapprocher"}
          </button>
          <button
            onClick={loadReport}
            disabled={loadingReport}
            className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-4 py-2 text-sm text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
          >
            {loadingReport ? "…" : "Voir le rapport"}
          </button>
        </div>

        {/* Reconciliation report */}
        {report && (
          <div className={`rounded-xl border-2 p-5 ${report.is_balanced ? "border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20" : "border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20"}`}>
            <div className="flex justify-between items-start mb-3">
              <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">Rapport de rapprochement</h3>
              <span className={`text-xs font-medium rounded-full px-2 py-0.5 ${report.is_balanced ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400" : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400"}`}>
                {report.is_balanced ? "Équilibré ✓" : "Écart détecté"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div><p className="text-zinc-400 text-xs">Rapproché côté relevé</p><p className="font-semibold tabular-nums">{fmt(report.sum_matched_bank)}</p></div>
              <div><p className="text-zinc-400 text-xs">Rapproché côté compta</p><p className="font-semibold tabular-nums">{fmt(report.sum_matched_accounting)}</p></div>
              <div><p className="text-zinc-400 text-xs">Lignes non rapprochées (relevé)</p><p className="font-semibold">{report.unmatched_bank_lines.length}</p></div>
              <div><p className="text-zinc-400 text-xs">Écritures non rapprochées (compta)</p><p className="font-semibold">{report.unmatched_accounting_entries.length}</p></div>
            </div>
          </div>
        )}

        {/* Lines table */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-zinc-100 dark:border-zinc-800 text-xs font-medium text-zinc-400 uppercase tracking-wide">
            Lignes du relevé ({total})
          </div>
          {statement.lines.length === 0 ? (
            <p className="text-sm text-zinc-400 text-center py-10">Aucune ligne.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-100 dark:border-zinc-800">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Date</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Libellé</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Montant</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Statut</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-zinc-400 uppercase">Écriture</th>
                    <th className="px-4 py-2.5" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                  {statement.lines.map((line) => (
                    <tr key={line.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/30">
                      <td className="px-4 py-2.5 whitespace-nowrap text-zinc-600 dark:text-zinc-400">
                        {fmtDate(line.transaction_date)}
                      </td>
                      <td className="px-4 py-2.5 max-w-xs truncate text-zinc-700 dark:text-zinc-300">
                        {line.label}
                      </td>
                      <td className={`px-4 py-2.5 text-right tabular-nums font-medium ${parseFloat(line.amount) < 0 ? "text-red-500" : "text-emerald-600"}`}>
                        {fmt(line.amount)}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge status={line.match_status} />
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-zinc-400">
                        {line.matched_reference ?? line.matched_account_code ?? "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex gap-1 justify-end">
                          {line.match_status === "unmatched" && (
                            <>
                              <button
                                onClick={() => handleOpenManualMatch(line)}
                                disabled={busyLine === line.id}
                                className="rounded-md bg-zinc-100 dark:bg-zinc-800 px-2 py-1 text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 disabled:opacity-50"
                              >
                                Matcher
                              </button>
                              <button
                                onClick={() => handleIgnore(line)}
                                disabled={busyLine === line.id}
                                className="rounded-md px-2 py-1 text-xs font-medium text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 disabled:opacity-50"
                              >
                                Ignorer
                              </button>
                            </>
                          )}
                          {(line.match_status === "matched" || line.match_status === "manual") && (
                            <button
                              onClick={() => handleUnmatch(line)}
                              disabled={busyLine === line.id}
                              className="rounded-md px-2 py-1 text-xs font-medium text-red-400 hover:text-red-600 disabled:opacity-50"
                            >
                              Dé-matcher
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ── Import form ───────────────────────────────────────────────────────────────

function ImportForm({ onImported }: { onImported: (s: BankStatement) => void }) {
  const [accountCode, setAccountCode] = useState("512");
  const [openingBalance, setOpeningBalance] = useState("0.00");
  const [closingBalance, setClosingBalance] = useState("0.00");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Veuillez sélectionner un fichier CSV.");
      return;
    }

    setBusy(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("account_code", accountCode);
    formData.append("opening_balance", openingBalance);
    formData.append("closing_balance", closingBalance);

    try {
      const res = await fetch("/api/bank-statements/import", {
        method: "POST",
        body: formData,
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? d.error ?? `Erreur ${res.status}`);
      onImported(d);
      if (fileRef.current) fileRef.current.value = "";
    } catch (ex: unknown) {
      setError(ex instanceof Error ? ex.message : "Erreur inconnue");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 space-y-4 shadow-sm"
    >
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
        Importer un relevé bancaire
      </h2>
      <p className="text-xs text-zinc-400">
        Format CSV : colonnes <code className="font-mono">date;libelle;montant</code> — séparateur ; ou ,
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-medium text-zinc-500 mb-1">Compte (512…)</label>
          <input
            type="text"
            value={accountCode}
            onChange={(e) => setAccountCode(e.target.value)}
            placeholder="512001"
            className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm font-mono text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-500 mb-1">Solde ouverture (€)</label>
          <input
            type="number"
            step="0.01"
            value={openingBalance}
            onChange={(e) => setOpeningBalance(e.target.value)}
            className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-500 mb-1">Solde clôture (€)</label>
          <input
            type="number"
            step="0.01"
            value={closingBalance}
            onChange={(e) => setClosingBalance(e.target.value)}
            className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
          />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-zinc-500 mb-1">Fichier CSV</label>
        <input
          type="file"
          accept=".csv,text/csv"
          ref={fileRef}
          className="text-sm text-zinc-600 dark:text-zinc-400 file:mr-3 file:rounded-lg file:border-0 file:bg-zinc-100 dark:file:bg-zinc-800 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-zinc-700 dark:file:text-zinc-300 hover:file:bg-zinc-200 dark:hover:file:bg-zinc-700"
        />
      </div>

      {error && <ErrorMsg msg={error} />}

      <button
        type="submit"
        disabled={busy}
        className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-5 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
      >
        {busy ? "Importation…" : "Importer"}
      </button>
    </form>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function BankPage() {
  const [statements, setStatements] = useState<BankStatement[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<BankStatement | null>(null);

  const loadStatements = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/bank-statements");
      const d = await res.json();
      if (!res.ok) throw new Error(d.error ?? "Erreur de chargement");
      setStatements(Array.isArray(d) ? d : d.results ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, []);

  // Load on first render
  useState(() => {
    loadStatements();
  });

  function handleImported(s: BankStatement) {
    setStatements((prev) => (prev ? [s, ...prev] : [s]));
    setSelected(s);
  }

  if (selected) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Rapprochement bancaire</h1>
        </div>
        <StatementDetail statement={selected} onBack={() => setSelected(null)} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Rapprochement bancaire</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Importez vos relevés bancaires CSV et rapprochez-les avec vos écritures comptables
        </p>
      </div>

      {/* Import form */}
      <ImportForm onImported={handleImported} />

      {/* Statements list */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">Relevés importés</h2>
          <button
            onClick={loadStatements}
            disabled={loading}
            className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 disabled:opacity-50"
          >
            {loading ? "…" : "Actualiser"}
          </button>
        </div>

        {error && <ErrorMsg msg={error} />}
        {loading && <LoadingSpinner />}

        {!loading && statements !== null && (
          <>
            {statements.length === 0 ? (
              <div className="rounded-xl border border-dashed border-zinc-200 dark:border-zinc-800 py-12 text-center">
                <p className="text-sm text-zinc-400">Aucun relevé importé. Commencez par importer un fichier CSV.</p>
              </div>
            ) : (
              <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-100 dark:border-zinc-800">
                      <th className="text-left px-4 py-3 text-xs font-medium text-zinc-400 uppercase">Compte</th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-zinc-400 uppercase">Période</th>
                      <th className="text-right px-4 py-3 text-xs font-medium text-zinc-400 uppercase">Lignes</th>
                      <th className="text-right px-4 py-3 text-xs font-medium text-zinc-400 uppercase">Rapprochées</th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-zinc-400 uppercase">Statut</th>
                      <th className="text-right px-4 py-3 text-xs font-medium text-zinc-400 uppercase">Importé le</th>
                      <th className="px-4 py-3" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                    {statements.map((s) => (
                      <tr
                        key={s.id}
                        className="hover:bg-zinc-50 dark:hover:bg-zinc-800/30 cursor-pointer"
                        onClick={() => setSelected(s)}
                      >
                        <td className="px-4 py-3 font-mono text-xs font-medium text-zinc-700 dark:text-zinc-300">
                          {s.account_code}
                          {s.account_label ? <span className="ml-1.5 font-sans font-normal text-zinc-400">{s.account_label}</span> : null}
                        </td>
                        <td className="px-4 py-3 text-zinc-500">
                          {fmtDate(s.period_from)} → {fmtDate(s.period_to)}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{s.lines_count}</td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          <span className={s.matched_count === s.lines_count && s.lines_count > 0 ? "text-emerald-600 font-medium" : "text-zinc-600 dark:text-zinc-400"}>
                            {s.matched_count}/{s.lines_count}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <StatBadge status={s.status} />
                        </td>
                        <td className="px-4 py-3 text-right text-zinc-400 text-xs">
                          {fmtDate(s.created_at)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className="text-xs text-zinc-400">Ouvrir →</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
