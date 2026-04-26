"use client";

import { useState, useCallback } from "react";

// ── Types ────────────────────────────────────────────────────────────────────

type Tab = "cdr" | "bilan" | "tva";

interface CdrSection {
  lines: { account_code: string; account_label: string; net: string }[];
  total: string;
}

interface CompteDeResultat {
  period: { from: string; to: string };
  produits: {
    exploitation: CdrSection;
    financier: CdrSection;
    exceptionnel: CdrSection;
    total: string;
  };
  charges: {
    exploitation: CdrSection;
    personnel: CdrSection;
    amortissements: CdrSection;
    financier: CdrSection;
    exceptionnel: CdrSection;
    impots: CdrSection;
    total: string;
  };
  resultat_net: string;
  resultat_type: "benefice" | "perte";
}

interface BilanSection {
  lines: { account_code: string; account_label: string; net: string }[];
  total: string;
}

interface Bilan {
  at: string;
  actif: {
    immobilisations: { nettes: string };
    stocks: BilanSection;
    clients: BilanSection;
    autres_creances: BilanSection;
    tresorerie: BilanSection;
    total: string;
  };
  passif: {
    capitaux_propres: { total: string };
    resultat_exercice: string;
    resultat_type: string;
    provisions: BilanSection;
    emprunts: BilanSection;
    fournisseurs: BilanSection;
    dettes_fiscales: BilanSection;
    autres_dettes: BilanSection;
    total: string;
  };
  ecart_bilan: string;
}

interface TvaCA3 {
  period: { from: string; to: string };
  tva_collectee: {
    total: string;
    lines: { account_code: string; account_label: string; net: string }[];
  };
  tva_deductible: {
    total: string;
    lines: { account_code: string; account_label: string; net: string }[];
  };
  solde_net: string;
  resultat: "tva_a_payer" | "credit_tva" | "equilibre";
  compte_solde: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatAmount(value: string | null | undefined): string {
  if (!value) return "—";
  const num = parseFloat(value);
  if (isNaN(num)) return "—";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(num);
}

function currentYear(): number {
  return new Date().getFullYear();
}

function isoDate(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

// ── Fetchers ─────────────────────────────────────────────────────────────────

async function apiFetch<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionTable({
  title,
  rows,
  total,
}: {
  title: string;
  rows: { account_code: string; account_label: string; net: string }[];
  total: string;
}) {
  if (rows.length === 0) return null;
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-2">{title}</h3>
      <table className="w-full text-sm mb-1">
        <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
          {rows.map((r) => (
            <tr key={r.account_code} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/30">
              <td className="py-1.5 font-mono text-xs text-zinc-400 w-16">{r.account_code}</td>
              <td className="py-1.5 text-zinc-600 dark:text-zinc-400">{r.account_label}</td>
              <td className="py-1.5 text-right tabular-nums text-zinc-700 dark:text-zinc-300">
                {formatAmount(r.net)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-zinc-200 dark:border-zinc-700">
            <td colSpan={2} className="py-1.5 text-xs font-semibold text-zinc-500">
              Sous-total
            </td>
            <td className="py-1.5 text-right font-semibold tabular-nums text-zinc-800 dark:text-zinc-200">
              {formatAmount(total)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="h-6 w-6 rounded-full border-2 border-zinc-300 border-t-zinc-600 animate-spin" />
    </div>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-600 dark:text-red-400">
      {message}
    </div>
  );
}

// ── Tab content components ────────────────────────────────────────────────────

function CdrTab() {
  const year = currentYear();
  const [from, setFrom] = useState(isoDate(year, 1, 1));
  const [to, setTo] = useState(isoDate(year, 12, 31));
  const [data, setData] = useState<CompteDeResultat | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<CompteDeResultat>(
        `/api/reports/compte-de-resultat?from=${from}&to=${to}`
      );
      setData(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, [from, to]);

  return (
    <div className="space-y-6">
      {/* Period selector */}
      <div className="flex flex-wrap items-end gap-3">
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
          onClick={load}
          disabled={loading}
          className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
        >
          {loading ? "Chargement…" : "Calculer"}
        </button>
        {data && (
          <a
            href={`/api/reports/compte-de-resultat?from=${from}&to=${to}&format=csv`}
            className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-4 py-2 text-sm text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
          >
            Exporter CSV
          </a>
        )}
      </div>

      {error && <ErrorMessage message={error} />}
      {loading && <LoadingSpinner />}

      {data && !loading && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Produits */}
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50 mb-4">
              Produits
            </h2>
            <div className="space-y-4">
              <SectionTable
                title="Exploitation (70–75)"
                rows={data.produits.exploitation.lines}
                total={data.produits.exploitation.total}
              />
              <SectionTable
                title="Financiers (76)"
                rows={data.produits.financier.lines}
                total={data.produits.financier.total}
              />
              <SectionTable
                title="Exceptionnels (77–79)"
                rows={data.produits.exceptionnel.lines}
                total={data.produits.exceptionnel.total}
              />
            </div>
            <div className="border-t-2 border-emerald-200 dark:border-emerald-800 mt-4 pt-3 flex justify-between">
              <span className="font-bold text-zinc-800 dark:text-zinc-200">Total produits</span>
              <span className="font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
                {formatAmount(data.produits.total)}
              </span>
            </div>
          </div>

          {/* Charges */}
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50 mb-4">
              Charges
            </h2>
            <div className="space-y-4">
              <SectionTable
                title="Exploitation (60–63)"
                rows={data.charges.exploitation.lines}
                total={data.charges.exploitation.total}
              />
              <SectionTable
                title="Personnel (64)"
                rows={data.charges.personnel.lines}
                total={data.charges.personnel.total}
              />
              <SectionTable
                title="Amortissements (68)"
                rows={data.charges.amortissements.lines}
                total={data.charges.amortissements.total}
              />
              <SectionTable
                title="Financières (66)"
                rows={data.charges.financier.lines}
                total={data.charges.financier.total}
              />
              <SectionTable
                title="Exceptionnelles (67)"
                rows={data.charges.exceptionnel.lines}
                total={data.charges.exceptionnel.total}
              />
              <SectionTable
                title="Impôts (69)"
                rows={data.charges.impots.lines}
                total={data.charges.impots.total}
              />
            </div>
            <div className="border-t-2 border-red-200 dark:border-red-800 mt-4 pt-3 flex justify-between">
              <span className="font-bold text-zinc-800 dark:text-zinc-200">Total charges</span>
              <span className="font-bold tabular-nums text-red-500 dark:text-red-400">
                {formatAmount(data.charges.total)}
              </span>
            </div>
          </div>

          {/* Résultat net */}
          <div className="lg:col-span-2 rounded-xl border-2 border-zinc-300 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 p-6">
            <div className="flex justify-between items-center">
              <span className="text-base font-bold text-zinc-900 dark:text-zinc-50">
                Résultat net de l&apos;exercice
              </span>
              <div className="text-right">
                <span
                  className={`text-2xl font-bold tabular-nums ${
                    data.resultat_type === "benefice"
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-red-500 dark:text-red-400"
                  }`}
                >
                  {formatAmount(data.resultat_net)}
                </span>
                <p className="text-xs text-zinc-400 mt-0.5 capitalize">
                  {data.resultat_type === "benefice" ? "Bénéfice" : "Perte"}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function BilanTab() {
  const year = currentYear();
  const [at, setAt] = useState(isoDate(year, 12, 31));
  const [data, setData] = useState<Bilan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<Bilan>(`/api/reports/bilan?at=${at}`);
      setData(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, [at]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs font-medium text-zinc-500 mb-1">Date de clôture</label>
          <input
            type="date"
            value={at}
            onChange={(e) => setAt(e.target.value)}
            className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
          />
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
        >
          {loading ? "Chargement…" : "Calculer"}
        </button>
        {data && (
          <a
            href={`/api/reports/bilan?at=${at}&format=csv`}
            className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-4 py-2 text-sm text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
          >
            Exporter CSV
          </a>
        )}
      </div>

      {error && <ErrorMessage message={error} />}
      {loading && <LoadingSpinner />}

      {data && !loading && (
        <>
          {parseFloat(data.ecart_bilan) !== 0 && (
            <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-3 text-sm text-amber-700 dark:text-amber-400">
              ⚠ Écart de bilan détecté: {formatAmount(data.ecart_bilan)} — vérifiez l&apos;équilibre de vos écritures.
            </div>
          )}

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* ACTIF */}
            <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50 mb-4 uppercase tracking-wide">
                Actif
              </h2>
              <div className="space-y-3 text-sm">
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">Immobilisations nettes</span>
                  <span className="tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(data.actif.immobilisations.nettes)}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">Stocks</span>
                  <span className="tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(data.actif.stocks.total)}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">Clients et comptes rattachés</span>
                  <span className="tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(data.actif.clients.total)}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">Autres créances</span>
                  <span className="tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(data.actif.autres_creances.total)}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">Trésorerie (512)</span>
                  <span className="tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(data.actif.tresorerie.total)}</span>
                </div>
                <div className="border-t-2 border-blue-200 dark:border-blue-800 pt-3 flex justify-between font-bold">
                  <span className="text-zinc-800 dark:text-zinc-200">Total actif</span>
                  <span className="tabular-nums text-blue-600 dark:text-blue-400">{formatAmount(data.actif.total)}</span>
                </div>
              </div>
            </div>

            {/* PASSIF */}
            <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50 mb-4 uppercase tracking-wide">
                Passif
              </h2>
              <div className="space-y-3 text-sm">
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">Capitaux propres</span>
                  <span className="tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(data.passif.capitaux_propres.total)}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">
                    Résultat {data.passif.resultat_type === "benefice" ? "(bénéfice)" : "(perte)"}
                  </span>
                  <span
                    className={`tabular-nums ${
                      data.passif.resultat_type === "benefice"
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-red-500 dark:text-red-400"
                    }`}
                  >
                    {formatAmount(data.passif.resultat_exercice)}
                  </span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">Provisions</span>
                  <span className="tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(data.passif.provisions.total)}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">Emprunts</span>
                  <span className="tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(data.passif.emprunts.total)}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">Fournisseurs</span>
                  <span className="tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(data.passif.fournisseurs.total)}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">Dettes fiscales et sociales</span>
                  <span className="tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(data.passif.dettes_fiscales.total)}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-zinc-500">Autres dettes</span>
                  <span className="tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(data.passif.autres_dettes.total)}</span>
                </div>
                <div className="border-t-2 border-blue-200 dark:border-blue-800 pt-3 flex justify-between font-bold">
                  <span className="text-zinc-800 dark:text-zinc-200">Total passif</span>
                  <span className="tabular-nums text-blue-600 dark:text-blue-400">{formatAmount(data.passif.total)}</span>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function TvaTab() {
  const year = currentYear();
  const [from, setFrom] = useState(isoDate(year, 1, 1));
  const [to, setTo] = useState(isoDate(year, 12, 31));
  const [data, setData] = useState<TvaCA3 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<TvaCA3>(`/api/tva/ca3?from=${from}&to=${to}`);
      setData(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, [from, to]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
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
          onClick={load}
          disabled={loading}
          className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
        >
          {loading ? "Chargement…" : "Calculer"}
        </button>
        {data && (
          <a
            href={`/api/tva/ca3?from=${from}&to=${to}&format=csv`}
            className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-4 py-2 text-sm text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
          >
            Exporter CSV
          </a>
        )}
      </div>

      {error && <ErrorMessage message={error} />}
      {loading && <LoadingSpinner />}

      {data && !loading && (
        <div className="space-y-4">
          {/* TVA collectée */}
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50 mb-4">
              TVA collectée
            </h2>
            {data.tva_collectee.lines.length === 0 ? (
              <p className="text-sm text-zinc-400">Aucun mouvement de TVA collectée.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-100 dark:border-zinc-800">
                    <th className="text-left py-1.5 text-xs font-medium text-zinc-400 uppercase">Compte</th>
                    <th className="text-left py-1.5 text-xs font-medium text-zinc-400 uppercase">Libellé</th>
                    <th className="text-right py-1.5 text-xs font-medium text-zinc-400 uppercase">Net</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                  {data.tva_collectee.lines.map((l) => (
                    <tr key={l.account_code} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/30">
                      <td className="py-1.5 font-mono text-xs text-zinc-400">{l.account_code}</td>
                      <td className="py-1.5 text-zinc-600 dark:text-zinc-400">{l.account_label}</td>
                      <td className="py-1.5 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(l.net)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-zinc-200 dark:border-zinc-700">
                    <td colSpan={2} className="py-1.5 font-semibold text-xs text-zinc-500">Total collectée</td>
                    <td className="py-1.5 text-right font-semibold tabular-nums">{formatAmount(data.tva_collectee.total)}</td>
                  </tr>
                </tfoot>
              </table>
            )}
          </div>

          {/* TVA déductible */}
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50 mb-4">
              TVA déductible
            </h2>
            {data.tva_deductible.lines.length === 0 ? (
              <p className="text-sm text-zinc-400">Aucun mouvement de TVA déductible.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-100 dark:border-zinc-800">
                    <th className="text-left py-1.5 text-xs font-medium text-zinc-400 uppercase">Compte</th>
                    <th className="text-left py-1.5 text-xs font-medium text-zinc-400 uppercase">Libellé</th>
                    <th className="text-right py-1.5 text-xs font-medium text-zinc-400 uppercase">Net</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800">
                  {data.tva_deductible.lines.map((l) => (
                    <tr key={l.account_code} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/30">
                      <td className="py-1.5 font-mono text-xs text-zinc-400">{l.account_code}</td>
                      <td className="py-1.5 text-zinc-600 dark:text-zinc-400">{l.account_label}</td>
                      <td className="py-1.5 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{formatAmount(l.net)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-zinc-200 dark:border-zinc-700">
                    <td colSpan={2} className="py-1.5 font-semibold text-xs text-zinc-500">Total déductible</td>
                    <td className="py-1.5 text-right font-semibold tabular-nums">{formatAmount(data.tva_deductible.total)}</td>
                  </tr>
                </tfoot>
              </table>
            )}
          </div>

          {/* Solde net */}
          <div
            className={`rounded-xl border-2 p-6 ${
              data.resultat === "tva_a_payer"
                ? "border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20"
                : data.resultat === "credit_tva"
                ? "border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20"
                : "border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800"
            }`}
          >
            <div className="flex justify-between items-center">
              <div>
                <p className="font-bold text-zinc-900 dark:text-zinc-50">
                  {data.resultat === "tva_a_payer"
                    ? "TVA à payer"
                    : data.resultat === "credit_tva"
                    ? "Crédit de TVA"
                    : "Équilibre"}
                </p>
                {data.compte_solde && (
                  <p className="text-xs text-zinc-400 font-mono mt-0.5">
                    Compte {data.compte_solde}
                  </p>
                )}
              </div>
              <span
                className={`text-2xl font-bold tabular-nums ${
                  data.resultat === "tva_a_payer"
                    ? "text-red-600 dark:text-red-400"
                    : data.resultat === "credit_tva"
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-zinc-700 dark:text-zinc-300"
                }`}
              >
                {formatAmount(data.solde_net)}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string }[] = [
  { id: "cdr", label: "Compte de résultat" },
  { id: "bilan", label: "Bilan" },
  { id: "tva", label: "TVA — CA3" },
];

export default function ReportsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("cdr");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Rapports financiers</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Compte de résultat, bilan comptable et déclaration TVA CA3
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === tab.id
                ? "border-zinc-900 dark:border-zinc-100 text-zinc-900 dark:text-zinc-100"
                : "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === "cdr" && <CdrTab />}
        {activeTab === "bilan" && <BilanTab />}
        {activeTab === "tva" && <TvaTab />}
      </div>
    </div>
  );
}
