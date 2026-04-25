"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const JOURNAL_CODES = [
  { code: "ACH", label: "ACH — Achats" },
  { code: "VTE", label: "VTE — Ventes" },
  { code: "BQ", label: "BQ — Banque" },
  { code: "OD", label: "OD — Opérations diverses" },
  { code: "CAI", label: "CAI — Caisse" },
];

interface Line {
  account_code: string;
  account_label: string;
  debit: string;
  credit: string;
}

const emptyLine = (): Line => ({
  account_code: "",
  account_label: "",
  debit: "",
  credit: "",
});

function parseAmount(val: string): number {
  const n = parseFloat(val.replace(",", "."));
  return isNaN(n) ? 0 : n;
}

export default function NewJournalEntryPage() {
  const router = useRouter();

  const [reference, setReference] = useState("");
  const [journalCode, setJournalCode] = useState("ACH");
  const [entryDate, setEntryDate] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [lines, setLines] = useState<Line[]>([emptyLine(), emptyLine()]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const updateLine = useCallback(
    (idx: number, field: keyof Line, value: string) => {
      setLines((prev) => {
        const next = [...prev];
        next[idx] = { ...next[idx], [field]: value };
        // Si on saisit un débit, vider crédit et vice-versa
        if (field === "debit" && value !== "") next[idx].credit = "";
        if (field === "credit" && value !== "") next[idx].debit = "";
        return next;
      });
    },
    []
  );

  const addLine = () => setLines((prev) => [...prev, emptyLine()]);

  const removeLine = (idx: number) => {
    if (lines.length <= 2) return; // minimum 2 lignes
    setLines((prev) => prev.filter((_, i) => i !== idx));
  };

  const totalDebit = lines.reduce((s, l) => s + parseAmount(l.debit), 0);
  const totalCredit = lines.reduce((s, l) => s + parseAmount(l.credit), 0);
  const isBalanced = Math.abs(totalDebit - totalCredit) < 0.001;
  const hasLines = lines.every((l) => l.account_code.trim() !== "");

  const fmt = (n: number) =>
    n.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!isBalanced) {
      setError(`Écriture déséquilibrée : débit ${fmt(totalDebit)} ≠ crédit ${fmt(totalCredit)}.`);
      return;
    }
    if (!hasLines) {
      setError("Tous les comptes PCG sont obligatoires.");
      return;
    }

    setLoading(true);
    try {
      const payload = {
        reference,
        journal_code: journalCode,
        entry_date: entryDate,
        lines: lines.map((l) => ({
          account_code: l.account_code.trim(),
          account_label: l.account_label.trim(),
          debit: parseAmount(l.debit).toFixed(2),
          credit: parseAmount(l.credit).toFixed(2),
        })),
      };

      const res = await fetch("/api/journal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const msg =
          data?.non_field_errors?.[0] ??
          data?.detail ??
          Object.values(data).flat().join(" ") ??
          "Erreur lors de la création.";
        setError(String(msg));
        return;
      }

      router.push("/app/ledger");
      router.refresh();
    } catch {
      setError("Impossible de joindre le serveur.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* En-tête */}
      <div className="flex items-center gap-3">
        <Link
          href="/app/ledger"
          className="text-sm text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
        >
          ← Retour
        </Link>
        <span className="text-zinc-300 dark:text-zinc-700">/</span>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          Nouvelle écriture
        </h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Champs en-tête */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 space-y-4">
          <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Informations générales
          </h2>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1">
              <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">
                Date
              </label>
              <input
                type="date"
                required
                value={entryDate}
                onChange={(e) => setEntryDate(e.target.value)}
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:focus:ring-zinc-50"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">
                Journal
              </label>
              <select
                value={journalCode}
                onChange={(e) => setJournalCode(e.target.value)}
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:focus:ring-zinc-50"
              >
                {JOURNAL_CODES.map(({ code, label }) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">
                Référence
              </label>
              <input
                type="text"
                placeholder="ex. FACT-2026-001"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-50 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 dark:focus:ring-zinc-50"
              />
            </div>
          </div>
        </div>

        {/* Lignes d'écriture */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden">
          <div className="px-6 py-4 border-b border-zinc-100 dark:border-zinc-800 flex items-center justify-between">
            <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Lignes d'écriture
            </h2>
            <button
              type="button"
              onClick={addLine}
              className="text-xs text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-50 transition-colors"
            >
              + Ajouter une ligne
            </button>
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
                <th className="w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {lines.map((line, idx) => (
                <tr key={idx}>
                  <td className="px-3 py-2">
                    <input
                      type="text"
                      placeholder="401"
                      value={line.account_code}
                      onChange={(e) => updateLine(idx, "account_code", e.target.value)}
                      className="w-full rounded border border-zinc-200 dark:border-zinc-700 bg-transparent px-2 py-1.5 font-mono text-sm text-zinc-900 dark:text-zinc-50 placeholder-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="text"
                      placeholder="Fournisseurs"
                      value={line.account_label}
                      onChange={(e) => updateLine(idx, "account_label", e.target.value)}
                      className="w-full rounded border border-zinc-200 dark:border-zinc-700 bg-transparent px-2 py-1.5 text-sm text-zinc-900 dark:text-zinc-50 placeholder-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder="0,00"
                      value={line.debit}
                      onChange={(e) => updateLine(idx, "debit", e.target.value)}
                      className="w-full rounded border border-zinc-200 dark:border-zinc-700 bg-transparent px-2 py-1.5 text-right tabular-nums text-sm text-zinc-900 dark:text-zinc-50 placeholder-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder="0,00"
                      value={line.credit}
                      onChange={(e) => updateLine(idx, "credit", e.target.value)}
                      className="w-full rounded border border-zinc-200 dark:border-zinc-700 bg-transparent px-2 py-1.5 text-right tabular-nums text-sm text-zinc-900 dark:text-zinc-50 placeholder-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
                    />
                  </td>
                  <td className="px-2 py-2 text-center">
                    <button
                      type="button"
                      onClick={() => removeLine(idx)}
                      disabled={lines.length <= 2}
                      className="text-zinc-300 dark:text-zinc-700 hover:text-red-500 dark:hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-base leading-none"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
            {/* Totaux */}
            <tfoot>
              <tr className="border-t-2 border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/50">
                <td
                  colSpan={2}
                  className="px-4 py-3 text-right text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wide"
                >
                  Total
                </td>
                <td className="px-4 py-3 text-right tabular-nums font-semibold text-zinc-900 dark:text-zinc-50">
                  {fmt(totalDebit)}
                </td>
                <td
                  className={`px-4 py-3 text-right tabular-nums font-semibold ${
                    isBalanced
                      ? "text-zinc-900 dark:text-zinc-50"
                      : "text-red-600 dark:text-red-400"
                  }`}
                >
                  {fmt(totalCredit)}
                </td>
                <td />
              </tr>
              {!isBalanced && (totalDebit > 0 || totalCredit > 0) && (
                <tr>
                  <td
                    colSpan={5}
                    className="px-4 py-2 text-right text-xs text-red-500 dark:text-red-400"
                  >
                    Écart : {fmt(Math.abs(totalDebit - totalCredit))} €
                  </td>
                </tr>
              )}
            </tfoot>
          </table>
        </div>

        {/* Erreur + Actions */}
        {error && (
          <p
            role="alert"
            className="rounded-lg bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-400"
          >
            {error}
          </p>
        )}

        <div className="flex items-center justify-end gap-3">
          <Link
            href="/app/ledger"
            className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-4 py-2 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
          >
            Annuler
          </Link>
          <button
            type="submit"
            disabled={loading || !isBalanced || !hasLines}
            className="rounded-lg bg-zinc-900 dark:bg-zinc-50 px-5 py-2 text-sm font-medium text-zinc-50 dark:text-zinc-900 hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Enregistrement…" : "Enregistrer l'écriture"}
          </button>
        </div>
      </form>
    </div>
  );
}
