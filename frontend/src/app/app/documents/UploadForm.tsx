"use client";

import { useRef, useState } from "react";

interface UploadResult {
  invoice_id: string;
  job_id: string;
  status: string;
  message: string;
}

interface UploadError {
  error?: string;
  detail?: string;
}

/**
 * Client Component — drag-and-drop / file picker for invoice PDFs.
 *
 * POSTs to /api/documents/upload (Next.js proxy → Django).
 * On success, calls onSuccess(result) so the parent page can refresh the list.
 * Calls onUploadStart() the moment the HTTP request is fired, so the parent
 * can immediately show a "loading document" indicator without waiting for the
 * first polling cycle.
 */
export default function UploadForm({
  onSuccess,
  onUploadStart,
}: {
  onSuccess: (r: UploadResult) => void;
  onUploadStart?: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setError(null);

    if (file.type !== "application/pdf" && !file.name.endsWith(".pdf")) {
      setError("Seuls les fichiers PDF sont acceptés.");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setError("Le fichier dépasse la limite de 20 Mo.");
      return;
    }

    setUploading(true);
    onUploadStart?.();
    try {
      const body = new FormData();
      body.append("file", file);

      const res = await fetch("/api/documents/upload", {
        method: "POST",
        body,
      });

      const json: UploadResult & UploadError = await res.json();

      if (!res.ok) {
        setError(
          json.detail ?? json.error ?? `Erreur serveur (${res.status})`
        );
        return;
      }

      onSuccess(json as UploadResult);
    } catch {
      setError("Erreur réseau, veuillez réessayer.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 transition-colors ${uploading ? "pointer-events-none opacity-60" : ""}`}
        style={{
          background: dragging ? "rgba(245,158,11,0.04)" : "var(--bg-root)",
          borderColor: dragging ? "var(--amber-500)" : "var(--border)",
        }}
      >
        <span className="text-3xl">📄</span>
        <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          {uploading
            ? "Envoi en cours…"
            : "Glissez un PDF ou cliquez pour parcourir"}
        </p>
        <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
          PDF uniquement · max 20 Mo
        </p>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={onInputChange}
        disabled={uploading}
      />

      {error && (
        <p className="rounded-lg px-4 py-2 text-sm" style={{ background: "var(--danger-bg)", color: "var(--danger)" }}>
          {error}
        </p>
      )}
    </div>
  );
}
