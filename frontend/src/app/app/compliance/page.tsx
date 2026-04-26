"use client";

import { useState } from "react";

function currentYear() {
  return new Date().getFullYear();
}

function isoDate(year: number, month: number, day: number) {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

// ── FEC Export section ────────────────────────────────────────────────────────

function FecExportSection() {
  const year = currentYear();
  const [from, setFrom] = useState(isoDate(year, 1, 1));
  const [to, setTo] = useState(isoDate(year, 12, 31));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastExport, setLastExport] = useState<string | null>(null);

  async function handleExport() {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ from, to });
      const res = await fetch(`/api/journal/export/fec?${params}`);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? data.error ?? `Erreur ${res.status}`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      a.href = url;
      a.download = match?.[1] ?? `FEC_${from}_${to}.txt`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      setLastExport(new Date().toLocaleString("fr-FR"));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-zinc-100 dark:border-zinc-800">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-lg bg-zinc-100 dark:bg-zinc-800 p-2 text-lg">🗂</div>
          <div>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              Fichier des Écritures Comptables (FEC)
            </h3>
            <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
              Format DGFiP — Article L.47 A du Livre des Procédures Fiscales. Fichier texte délimité, encodage UTF-8.
            </p>
          </div>
        </div>
      </div>

      <div className="p-5 space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Exercice — du</label>
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">au</label>
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            />
          </div>
          <button
            onClick={handleExport}
            disabled={loading}
            className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
          >
            {loading ? "Génération…" : "↓ Télécharger FEC"}
          </button>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}
        {lastExport && !error && (
          <p className="text-xs text-emerald-600 dark:text-emerald-400">✓ Dernier export : {lastExport}</p>
        )}

        <div className="rounded-lg bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-100 dark:border-zinc-800 p-4 space-y-2">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Colonnes FEC (norme DGFiP)</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400 font-mono">
            {["JournalCode", "JournalLib", "EcritureNum", "EcritureDate", "CompteNum", "CompteLib", "CompAuxNum", "CompAuxLib", "PieceRef", "PieceDate", "EcritureLib", "Debit", "Credit", "EcritureLet", "DateLet", "ValidDate", "Montantdevise", "Idevise"].map((col) => (
              <span key={col}>{col}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Checklist section ─────────────────────────────────────────────────────────

interface CheckItem {
  id: string;
  label: string;
  description: string;
  status: "ok" | "warning" | "info";
}

const COMPLIANCE_CHECKS: CheckItem[] = [
  {
    id: "fec",
    label: "Export FEC disponible",
    description: "Le fichier FEC peut être généré à tout moment pour contrôle fiscal.",
    status: "ok",
  },
  {
    id: "balance",
    label: "Balance de vérification",
    description: "Accessible depuis Exports — vérifier l'équilibre débit/crédit.",
    status: "ok",
  },
  {
    id: "lettrage",
    label: "Lettrage des comptes de tiers",
    description: "Les comptes clients/fournisseurs (4xx) doivent être lettrés régulièrement.",
    status: "ok",
  },
  {
    id: "journal",
    label: "Journaux obligatoires (ACH, VTE, BQ, OD)",
    description: "Les journaux réglementaires sont configurés.",
    status: "ok",
  },
  {
    id: "pcg",
    label: "Plan de comptes PCG",
    description: "Vérifier la conformité du plan de comptes à la nomenclature PCG 2005.",
    status: "info",
  },
  {
    id: "tva",
    label: "Déclaration TVA CA3",
    description: "Accessible depuis Rapports. Vérifier les montants avant dépôt DGFiP.",
    status: "warning",
  },
];

const STATUS_ICON: Record<string, string> = { ok: "✓", warning: "⚠", info: "ℹ" };
const STATUS_STYLE: Record<string, string> = {
  ok: "border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950/20",
  warning: "border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/20",
  info: "border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/50",
};
const ICON_STYLE: Record<string, string> = {
  ok: "text-emerald-600 dark:text-emerald-400",
  warning: "text-amber-600 dark:text-amber-400",
  info: "text-zinc-500 dark:text-zinc-400",
};

function ComplianceChecklist() {
  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-zinc-100 dark:border-zinc-800">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-lg bg-zinc-100 dark:bg-zinc-800 p-2 text-lg">✓</div>
          <div>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              Points de conformité réglementaire
            </h3>
            <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
              Exigences comptables et fiscales françaises (PCG, CGI, LPF).
            </p>
          </div>
        </div>
      </div>
      <div className="p-5 space-y-2">
        {COMPLIANCE_CHECKS.map((item) => (
          <div key={item.id} className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${STATUS_STYLE[item.status]}`}>
            <span className={`text-sm font-bold mt-0.5 ${ICON_STYLE[item.status]}`}>{STATUS_ICON[item.status]}</span>
            <div>
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{item.label}</p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">{item.description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CompliancePage() {
  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Conformité</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Export FEC DGFiP et contrôle des obligations réglementaires.
        </p>
      </div>
      <FecExportSection />
      <ComplianceChecklist />
    </div>
  );
}
