"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

interface ValidateButtonsProps {
  entryId: string;
}

export default function ValidateButtons({ entryId }: ValidateButtonsProps) {
  const router = useRouter();
  const [loading, setLoading] = useState<"validate" | "cancel" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleValidate() {
    if (!confirm("Valider cette écriture ? Cette action est définitive.")) return;
    setLoading("validate");
    setError(null);
    try {
      const res = await fetch(`/api/journal/${entryId}/validate`, {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? data.error ?? "Erreur lors de la validation.");
      } else {
        router.refresh();
      }
    } catch {
      setError("Erreur réseau. Veuillez réessayer.");
    } finally {
      setLoading(null);
    }
  }

  async function handleCancel() {
    if (!confirm("Annuler cette écriture ? Elle passera en statut « Annulé ».")) return;
    setLoading("cancel");
    setError(null);
    try {
      const res = await fetch(`/api/journal/${entryId}/cancel`, {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? data.error ?? "Erreur lors de l'annulation.");
      } else {
        router.refresh();
      }
    } catch {
      setError("Erreur réseau. Veuillez réessayer.");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-3">
        <button
          onClick={handleCancel}
          disabled={loading !== null}
          className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading === "cancel" ? "Annulation…" : "Annuler l'écriture"}
        </button>
        <button
          onClick={handleValidate}
          disabled={loading !== null}
          className="rounded-lg bg-emerald-600 hover:bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading === "validate" ? "Validation…" : "Valider l'écriture"}
        </button>
      </div>
      {error && (
        <p className="text-xs text-red-600 dark:text-red-400 max-w-xs text-right">
          {error}
        </p>
      )}
    </div>
  );
}
