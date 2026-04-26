"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import FecExportButton from "./FecExportButton";

// ── Types ─────────────────────────────────────────────────────────────────────

interface AccountEntry {
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
  status: "draft" | "posted" | "cancelled";
  lines: AccountEntry[];
  created_at: string;
}

interface PaginatedResponse {
  count?: number;
  results?: JournalEntry[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const JOURNALS = [
  { value: "", label: "Tous les journaux" },
  { value: "ACH", label: "ACH — Achats" },
  { value: "VTE", label: "VTE — Ventes" },
  { value: "BQ", label: "BQ — Banque" },
  { value: "OD", label: "OD — Opérations diverses" },
  { value: "CAI", label: "CAI — Caisse" },
];

const JOURNAL_LABELS: Record<string, string> = {
  ACH: "Achats",
  VTE: "Ventes",
  BQ: "Banque",
  OD: "Opér. diverses",
  CAI: "Caisse",
};

const STATUSES = [
  { value: "", label: "Tous les statuts" },
  { value: "draft", label: "Brouillon" },
  { value: "posted", label: "Comptabilisé" },
  { value: "cancelled", label: "Annulé" },
];

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400",
  posted: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
  cancelled: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Brouillon",
  posted: "Comptabilisé",
  cancelled: "Annulé",
};

const STATUS_DOT: Record<string, string> = {
  draft: "bg-amber-400",
  posted: "bg-emerald-500",
  cancelled: "bg-red-500",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function sumLines(lines: AccountEntry[], field: "debit" | "credit") {
  const total = lines.reduce((acc, l) => acc + parseFloat(l[field] || "0"), 0);
  return total.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function StatsBar({ entries }: { entries: JournalEntry[] }) {
  const counts = {
    draft: entries.filter((e) => e.status === "draft").length,
    posted: entries.filter((e) => e.status === "posted").length,
    cancelled: entries.filter((e) => e.status === "cancelled").length,
  };

  return (
    <div className="grid grid-cols-3 gap-3">
      {(["draft", "posted", "cancelled"] as const).map((s) => (
        <div
          key={s}
          className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-4 py-3"
        >
          <div className="flex items-center gap-2 mb-1">
            <span className={`h-2 w-2 rounded-full ${STATUS_DOT[s]}`} />
            <span className="text-xs text-zinc-500 dark:text-zinc-400">{STATUS_LABELS[s]}</span>
          </div>
          <p className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">{counts[s]}</p>
        </div>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20;

export default function LedgerPage() {
  const [allEntries, setAllEntries] = useState<JournalEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [journal, setJournal] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page_size: "200" });
      const res = await fetch(`/api/journal?${params}`);
      if (!res.ok) throw new Error(`Erreur ${res.status}`);
      const data: PaginatedResponse | JournalEntry[] = await res.json();
      const entries = Array.isArray(data) ? data : (data.results ?? []);
      setAllEntries(entries);
      setTotal(Array.isArray(data) ? data.length : (data.count ?? entries.length));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Reset page on filter change
  useEffect(() => { setPage(1); }, [search, journal, status]);

  // Client-side filtering
  const filtered = allEntries.filter((e) => {
    if (journal && e.journal_code !== journal) return false;
    if (status && e.status !== status) return false;
    if (search) {
      const q = search.toLowerCase();
      if (
        !e.reference?.toLowerCase().includes(q) &&
        !(JOURNAL_LABELS[e.journal_code] ?? "").toLowerCase().includes(q)
      )
        return false;
    }
    return true;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
            Journal des écritures
          </h1>
          <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
            {loading ? "Chargement…" : `${total} écriture${total !== 1 ? "s" : ""}`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <FecExportButton />
          <Link
            href="/app/ledger/new"
            className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 dark:bg-zinc-50 px-4 py-2 text-sm font-medium text-zinc-50 dark:text-zinc-900 hover:bg-zinc-700 dark:hover:bg-zinc-200 transition-colors"
          >
            + Nouvelle écriture
          </Link>
        </div>
      </div>

      {/* Stats bar */}
      {!loading && allEntries.length > 0 && <StatsBar entries={allEntries} />}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          type="search"
          placeholder="Référence…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 w-48"
        />
        <select
          value={journal}
          onChange={(e) => setJournal(e.target.value)}
          className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
        >
          {JOURNALS.map((j) => (
            <option key={j.value} value={j.value}>{j.label}</option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-400"
        >
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        {(search || journal || status) && (
          <button
            onClick={() => { setSearch(""); setJournal(""); setStatus(""); }}
            className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-2 text-sm text-zinc-500 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
          >
            Réinitialiser
          </button>
        )}
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
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-12 rounded-xl bg-zinc-100 dark:bg-zinc-800 animate-pulse" />
          ))}
        </div>
      ) : paginated.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 py-20 gap-3 text-center">
          <div className="rounded-full bg-zinc-100 dark:bg-zinc-800 p-4 text-2xl">≡</div>
          <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Aucune écriture</p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-xs">
            {search || journal || status
              ? "Aucun résultat pour ces filtres."
              : "Créez votre première écriture comptable."}
          </p>
          {!search && !journal && !status && (
            <Link
              href="/app/ledger/new"
              className="mt-2 rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2 text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-200 transition-colors"
            >
              + Nouvelle écriture
            </Link>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100 dark:border-zinc-800 text-xs text-zinc-500 dark:text-zinc-400">
                <th className="px-4 py-3 text-left font-medium">Date</th>
                <th className="px-4 py-3 text-left font-medium">Référence</th>
                <th className="px-4 py-3 text-left font-medium">Journal</th>
                <th className="px-4 py-3 text-left font-medium">Statut</th>
                <th className="px-4 py-3 text-right font-medium hidden sm:table-cell">Débit (€)</th>
                <th className="px-4 py-3 text-right font-medium hidden sm:table-cell">Crédit (€)</th>
                <th className="px-4 py-3 text-center font-medium hidden md:table-cell">Lignes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {paginated.map((entry) => (
                <tr
                  key={entry.id}
                  className="hover:bg-zinc-50 dark:hover:bg-zinc-800/40 transition-colors"
                >
                  <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300 tabular-nums whitespace-nowrap">
                    {formatDate(entry.entry_date)}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/app/ledger/${entry.id}`}
                      className="font-medium text-zinc-900 dark:text-zinc-50 hover:underline font-mono text-xs"
                    >
                      {entry.reference || <span className="text-zinc-400 font-sans font-normal">—</span>}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    <span className="font-mono text-xs bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">
                      {entry.journal_code}
                    </span>
                    <span className="ml-2 text-zinc-500 dark:text-zinc-500 hidden lg:inline">
                      {JOURNAL_LABELS[entry.journal_code] ?? entry.journal_code}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[entry.status] ?? ""}`}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[entry.status] ?? ""}`} />
                      {STATUS_LABELS[entry.status] ?? entry.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-zinc-700 dark:text-zinc-300 hidden sm:table-cell">
                    {sumLines(entry.lines, "debit")}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-zinc-700 dark:text-zinc-300 hidden sm:table-cell">
                    {sumLines(entry.lines, "credit")}
                  </td>
                  <td className="px-4 py-3 text-center text-zinc-400 hidden md:table-cell">
                    {entry.lines.length}
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
            {filtered.length !== allEntries.length && (
              <span className="ml-2 text-xs">({filtered.length} résultats filtrés)</span>
            )}
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
    </div>
  );
}

const API_BASE =
  process.env.DJANGO_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://api.localhost:8888";

const JOURNAL_LABELS: Record<string, string> = {
  ACH: "Achats",
  VTE: "Ventes",
  BQ: "Banque",
  OD: "Opérations diverses",
  CAI: "Caisse",
};

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  posted: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
  cancelled: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Brouillon",
  posted: "Comptabilisé",
  cancelled: "Annulé",
};

interface AccountEntry {
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
  status: "draft" | "posted" | "cancelled";
  lines: AccountEntry[];
  created_at: string;
}

interface PaginatedResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: JournalEntry[];
}

async function fetchJournal(): Promise<PaginatedResponse | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) return null;

  try {
    const res = await fetch(`${API_BASE}/api/v1/journal/`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function sumLines(lines: AccountEntry[], field: "debit" | "credit") {
  return lines
    .reduce((acc, l) => acc + parseFloat(l[field] || "0"), 0)
    .toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default async function LedgerPage() {
  const data = await fetchJournal();

  return (
    <div className="space-y-6">
      {/* En-tête */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
            Journal des écritures
          </h1>
          <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
            {data ? `${data.count} écriture${data.count !== 1 ? "s" : ""}` : "—"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <FecExportButton />
          <Link
            href="/app/ledger/new"
            className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 dark:bg-zinc-50 px-4 py-2 text-sm font-medium text-zinc-50 dark:text-zinc-900 hover:bg-zinc-700 dark:hover:bg-zinc-200 transition-colors"
          >
            + Nouvelle écriture
          </Link>
        </div>
      </div>

      {/* Tableau */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden">
        {!data || data.results.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <p className="text-zinc-400 dark:text-zinc-500 text-sm">
              Aucune écriture pour le moment.
            </p>
            <Link
              href="/app/ledger/new"
              className="mt-4 text-sm font-medium text-zinc-900 dark:text-zinc-50 underline underline-offset-4"
            >
              Créer la première écriture
            </Link>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/50">
                <th className="px-4 py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">
                  Date
                </th>
                <th className="px-4 py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">
                  Référence
                </th>
                <th className="px-4 py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">
                  Journal
                </th>
                <th className="px-4 py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">
                  Statut
                </th>
                <th className="px-4 py-3 text-right font-medium text-zinc-500 dark:text-zinc-400">
                  Débit (€)
                </th>
                <th className="px-4 py-3 text-right font-medium text-zinc-500 dark:text-zinc-400">
                  Crédit (€)
                </th>
                <th className="px-4 py-3 text-center font-medium text-zinc-500 dark:text-zinc-400">
                  Lignes
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {data.results.map((entry) => (
                <tr
                  key={entry.id}
                  className="hover:bg-zinc-50 dark:hover:bg-zinc-800/40 transition-colors"
                >
                  <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300 tabular-nums">
                    {formatDate(entry.entry_date)}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/app/ledger/${entry.id}`}
                      className="font-medium text-zinc-900 dark:text-zinc-50 hover:underline"
                    >
                      {entry.reference || <span className="text-zinc-400">—</span>}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                    <span className="font-mono text-xs bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">
                      {entry.journal_code}
                    </span>
                    <span className="ml-2 text-zinc-500 dark:text-zinc-500">
                      {JOURNAL_LABELS[entry.journal_code] ?? entry.journal_code}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[entry.status] ?? ""}`}
                    >
                      {STATUS_LABELS[entry.status] ?? entry.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-zinc-700 dark:text-zinc-300">
                    {sumLines(entry.lines, "debit")}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-zinc-700 dark:text-zinc-300">
                    {sumLines(entry.lines, "credit")}
                  </td>
                  <td className="px-4 py-3 text-center text-zinc-500 dark:text-zinc-400">
                    {entry.lines.length}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
