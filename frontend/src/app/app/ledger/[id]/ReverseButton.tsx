"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface Props {
  entryId: string;
}

/**
 * Button that creates a reversal (extourne) draft from a posted entry.
 *
 * Prompts for a reason via a small inline form before sending the request.
 * On success, navigates to the newly created reversal entry.
 */
export default function ReverseButton({ entryId }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reversalDate, setReversalDate] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleReverse() {
    if (!reason.trim()) {
      setError("Le motif est obligatoire.");
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`/api/journal/${entryId}/reverse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reason.trim(), reversal_date: reversalDate }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        setError(data?.detail ?? data?.error ?? "Erreur lors de l'extourne.");
        return;
      }

      // Navigate to the new reversal entry
      router.push(`/app/ledger/${data.id}`);
      router.refresh();
    } catch {
      setError("Impossible de contacter le serveur.");
    } finally {
      setLoading(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3" />
        </svg>
        Extourner
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-4 min-w-72">
      <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
        Créer une écriture d'extourne
      </p>
      <p className="text-xs text-amber-700 dark:text-amber-400">
        Une nouvelle écriture brouillon avec les débits/crédits inversés sera créée.
      </p>

      <div className="space-y-2 mt-1">
        <div>
          <label className="block text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1">
            Motif <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Ex: Facture annulée par le fournisseur"
            className="w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-900 px-3 py-1.5 text-sm text-zinc-900 dark:text-zinc-50 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1">
            Date de l'extourne
          </label>
          <input
            type="date"
            value={reversalDate}
            onChange={(e) => setReversalDate(e.target.value)}
            className="w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-900 px-3 py-1.5 text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-amber-500"
          />
        </div>
      </div>

      {error && (
        <p className="text-xs text-red-500 dark:text-red-400">{error}</p>
      )}

      <div className="flex gap-2 mt-1">
        <button
          onClick={handleReverse}
          disabled={loading}
          className="flex-1 rounded-md bg-amber-600 hover:bg-amber-700 disabled:opacity-50 px-3 py-1.5 text-sm font-medium text-white transition-colors"
        >
          {loading ? "En cours…" : "Confirmer l'extourne"}
        </button>
        <button
          onClick={() => { setOpen(false); setError(null); setReason(""); }}
          className="rounded-md border border-zinc-300 dark:border-zinc-600 px-3 py-1.5 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
        >
          Annuler
        </button>
      </div>
    </div>
  );
}
