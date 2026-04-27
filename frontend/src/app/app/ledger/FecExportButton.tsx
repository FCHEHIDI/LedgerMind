"use client";

import { useState } from "react";

/**
 * Button that triggers a FEC file download for the current year.
 *
 * Downloads via the Next.js proxy route /api/journal/export/fec which
 * forwards to Django GET /api/v1/journal/export/fec/.
 *
 * The browser receives a text/plain attachment and saves the file locally.
 */
export default function FecExportButton() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDownload() {
    setLoading(true);
    setError(null);

    const today = new Date();
    const year = today.getFullYear();
    const from = `${year}-01-01`;
    const to = today.toISOString().slice(0, 10);

    try {
      const res = await fetch(`/api/journal/export/fec?from=${from}&to=${to}`);

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data?.detail ?? data?.error ?? "Erreur lors de l'export FEC.");
        return;
      }

      // Trigger browser download
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match?.[1] ?? `export_fec_${year}.txt`;

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError("Impossible de contacter le serveur.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleDownload}
        disabled={loading}
        title="Exporter le Fichier des Écritures Comptables (FEC) pour l'année en cours"
        className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          color: "var(--text-primary)",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--amber-400)")}
        onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
      >
        {loading ? (
          <>
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            Export en cours…
          </>
        ) : (
          <>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 16v-8m0 8l-3-3m3 3l3-3M4 20h16" />
            </svg>
            Export FEC
          </>
        )}
      </button>
      {error && (
        <p className="text-xs max-w-xs text-right" style={{ color: "var(--danger)" }}>{error}</p>
      )}
    </div>
  );
}
