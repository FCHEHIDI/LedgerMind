"use client";

import { useState, useCallback, useEffect } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Account {
  id: string;
  account_code: string;
  account_label: string;
  account_class: number;
  account_type: string;
  is_system: boolean;
  is_active: boolean;
  parent_code: string | null;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const CLASS_LABELS: Record<number, string> = {
  1: "Classe 1 — Comptes de capitaux",
  2: "Classe 2 — Comptes d'immobilisations",
  3: "Classe 3 — Comptes de stocks",
  4: "Classe 4 — Comptes de tiers",
  5: "Classe 5 — Comptes financiers",
  6: "Classe 6 — Comptes de charges",
  7: "Classe 7 — Comptes de produits",
  8: "Classe 8 — Comptes spéciaux",
  9: "Classe 9 — Comptes analytiques",
};

const CLASS_COLORS: Record<number, string> = {
  1: "border-l-violet-400",
  2: "border-l-blue-400",
  3: "border-l-cyan-400",
  4: "border-l-amber-400",
  5: "border-l-emerald-400",
  6: "border-l-red-400",
  7: "border-l-green-400",
  8: "border-l-zinc-400",
  9: "border-l-zinc-300",
};

const TYPE_LABELS: Record<string, string> = {
  actif: "Actif",
  passif: "Passif",
  charge: "Charge",
  produit: "Produit",
  tiers: "Tiers",
  tresorerie: "Trésorerie",
  capital: "Capitaux",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function groupByClass(accounts: Account[]): Map<number, Account[]> {
  const map = new Map<number, Account[]>();
  for (const acc of accounts) {
    const cls = acc.account_class;
    if (!map.has(cls)) map.set(cls, []);
    map.get(cls)!.push(acc);
  }
  return new Map([...map.entries()].sort(([a], [b]) => a - b));
}

// ── Add account modal ─────────────────────────────────────────────────────────

interface AddAccountModalProps {
  onClose: () => void;
  onCreated: () => void;
}

function AddAccountModal({ onClose, onCreated }: AddAccountModalProps) {
  const [code, setCode] = useState("");
  const [label, setLabel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim() || !label.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/chart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_code: code.trim(), account_label: label.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.account_code?.[0] ?? data.detail ?? `Erreur ${res.status}`);
      onCreated();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur inconnue");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-2xl p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">Nouveau compte</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 text-xl leading-none">×</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Code PCG *</label>
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="ex: 401100"
              required
              className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 font-mono focus:outline-none focus:ring-2 focus:ring-zinc-400"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Libellé *</label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="ex: Fournisseurs divers"
              required
              className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            />
          </div>

          {error && (
            <p className="text-sm text-red-500">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-1">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100">
              Annuler
            </button>
            <button
              type="submit"
              disabled={submitting || !code.trim() || !label.trim()}
              className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 disabled:opacity-50 transition-colors"
            >
              {submitting ? "Création…" : "Créer"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PlanComptesPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterClass, setFilterClass] = useState("");
  const [filterActive, setFilterActive] = useState("true");
  const [showModal, setShowModal] = useState(false);
  const [expandedClasses, setExpandedClasses] = useState<Set<number>>(new Set([1, 2, 3, 4, 5, 6, 7]));

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filterClass) params.set("class", filterClass);
      if (filterActive) params.set("active", filterActive);
      if (search) params.set("search", search);
      const res = await fetch(`/api/chart?${params}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `Erreur ${res.status}`);
      // API may return paginated or plain array
      setAccounts(Array.isArray(data) ? data : (data.results ?? []));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, [filterClass, filterActive, search]);

  useEffect(() => { load(); }, [load]);

  async function handleSeedPcg() {
    setSeeding(true);
    try {
      const res = await fetch("/api/chart/seed-pcg", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `Erreur ${res.status}`);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue lors du seed PCG");
    } finally {
      setSeeding(false);
    }
  }

  function toggleClass(cls: number) {
    setExpandedClasses((prev) => {
      const next = new Set(prev);
      if (next.has(cls)) next.delete(cls);
      else next.add(cls);
      return next;
    });
  }

  const grouped = groupByClass(accounts);
  const totalActive = accounts.filter((a) => a.is_active).length;

  return (
    <div className="space-y-5">
      {showModal && (
        <AddAccountModal onClose={() => setShowModal(false)} onCreated={load} />
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Plan de comptes</h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            {loading ? "Chargement…" : `${accounts.length} compte${accounts.length !== 1 ? "s" : ""}${filterActive === "true" ? " actifs" : ""}`}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {accounts.length === 0 && !loading && (
            <button
              onClick={handleSeedPcg}
              disabled={seeding}
              className="rounded-lg border border-zinc-300 dark:border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-50 transition-colors"
            >
              {seeding ? "Import PCG…" : "⊕ Importer PCG standard"}
            </button>
          )}
          {accounts.length > 0 && (
            <button
              onClick={handleSeedPcg}
              disabled={seeding}
              title="Ajouter les comptes PCG manquants"
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-2 text-xs text-zinc-500 hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-50 transition-colors"
            >
              {seeding ? "Sync…" : "Sync PCG"}
            </button>
          )}
          <button
            onClick={() => setShowModal(true)}
            className="rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 transition-colors"
          >
            + Nouveau compte
          </button>
        </div>
      </div>

      {/* Stats bar */}
      {!loading && accounts.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {[...grouped.entries()].map(([cls, accs]) => (
            <div key={cls} className={`flex items-center gap-1.5 rounded-lg border-l-2 ${CLASS_COLORS[cls] ?? "border-l-zinc-300"} border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-3 py-1.5`}>
              <span className="text-xs font-bold text-zinc-500">Cl.{cls}</span>
              <span className="text-xs text-zinc-400">{accs.length}</span>
            </div>
          ))}
          <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/50 px-3 py-1.5">
            <span className="text-xs text-zinc-500">{totalActive} actifs / {accounts.length} total</span>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4 shadow-sm">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[160px]">
            <label className="block text-xs font-medium text-zinc-500 mb-1">Recherche</label>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Code ou libellé…"
              className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Classe</label>
            <select
              value={filterClass}
              onChange={(e) => setFilterClass(e.target.value)}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            >
              <option value="">Toutes</option>
              {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((c) => (
                <option key={c} value={String(c)}>Classe {c}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Statut</label>
            <select
              value={filterActive}
              onChange={(e) => setFilterActive(e.target.value)}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            >
              <option value="true">Actifs</option>
              <option value="false">Inactifs</option>
              <option value="">Tous</option>
            </select>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-10">
          <div className="h-5 w-5 rounded-full border-2 border-zinc-300 border-t-zinc-600 animate-spin" />
        </div>
      )}

      {/* Empty state */}
      {!loading && accounts.length === 0 && !error && (
        <div className="rounded-xl border border-dashed border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-6 py-14 text-center">
          <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">Aucun compte dans le plan de comptes.</p>
          <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
            Importez le plan PCG standard pour démarrer.
          </p>
          <button
            onClick={handleSeedPcg}
            disabled={seeding}
            className="mt-4 rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 disabled:opacity-50 transition-colors"
          >
            {seeding ? "Import en cours…" : "Importer le PCG standard"}
          </button>
        </div>
      )}

      {/* Account tree grouped by class */}
      {!loading && grouped.size > 0 && (
        <div className="space-y-3">
          {[...grouped.entries()].map(([cls, accs]) => {
            const isExpanded = expandedClasses.has(cls);
            const colorBorder = CLASS_COLORS[cls] ?? "border-l-zinc-300";
            return (
              <div key={cls} className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
                {/* Class header */}
                <button
                  onClick={() => toggleClass(cls)}
                  className={`w-full flex items-center justify-between px-4 py-3 border-l-4 ${colorBorder} hover:bg-zinc-50 dark:hover:bg-zinc-800/30 transition-colors`}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                      {CLASS_LABELS[cls] ?? `Classe ${cls}`}
                    </span>
                    <span className="text-xs text-zinc-400 bg-zinc-100 dark:bg-zinc-800 rounded-full px-2 py-0.5">
                      {accs.length}
                    </span>
                  </div>
                  <span className="text-xs text-zinc-300 dark:text-zinc-600">{isExpanded ? "▲" : "▼"}</span>
                </button>

                {/* Account rows */}
                {isExpanded && (
                  <div className="border-t border-zinc-100 dark:border-zinc-800">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-zinc-50 dark:bg-zinc-800/40">
                          <th className="text-left px-4 py-2 text-xs font-medium text-zinc-400 uppercase w-28">Code</th>
                          <th className="text-left px-4 py-2 text-xs font-medium text-zinc-400 uppercase">Libellé</th>
                          <th className="text-left px-4 py-2 text-xs font-medium text-zinc-400 uppercase hidden sm:table-cell">Type</th>
                          <th className="text-center px-4 py-2 text-xs font-medium text-zinc-400 uppercase">Système</th>
                          <th className="text-center px-4 py-2 text-xs font-medium text-zinc-400 uppercase">Statut</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-50 dark:divide-zinc-800/50">
                        {accs.map((acc) => (
                          <tr key={acc.id} className={`hover:bg-zinc-50 dark:hover:bg-zinc-800/20 ${!acc.is_active ? "opacity-50" : ""}`}>
                            <td className="px-4 py-2.5 font-mono text-xs text-zinc-500 dark:text-zinc-400 whitespace-nowrap">
                              {acc.account_code}
                            </td>
                            <td className="px-4 py-2.5 text-zinc-800 dark:text-zinc-200">
                              {acc.account_label}
                              {acc.parent_code && (
                                <span className="ml-2 text-xs text-zinc-400 font-mono">← {acc.parent_code}</span>
                              )}
                            </td>
                            <td className="px-4 py-2.5 hidden sm:table-cell">
                              {acc.account_type ? (
                                <span className="text-xs text-zinc-500 bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">
                                  {TYPE_LABELS[acc.account_type] ?? acc.account_type}
                                </span>
                              ) : <span className="text-zinc-300">—</span>}
                            </td>
                            <td className="px-4 py-2.5 text-center">
                              {acc.is_system ? (
                                <span className="text-xs text-zinc-400" title="Compte PCG standard">PCG</span>
                              ) : (
                                <span className="text-xs text-zinc-300 dark:text-zinc-600">—</span>
                              )}
                            </td>
                            <td className="px-4 py-2.5 text-center">
                              <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                                acc.is_active
                                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400"
                                  : "bg-zinc-100 text-zinc-400 dark:bg-zinc-800"
                              }`}>
                                {acc.is_active ? "Actif" : "Inactif"}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
