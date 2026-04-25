"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import UploadForm from "./UploadForm";

interface UploadResult {
  invoice_id: string;
  job_id: string;
  status: string;
  message: string;
}

/**
 * Client wrapper that handles upload success notifications and page refresh.
 *
 * Uses router.refresh() to re-fetch the invoice list from the Server Component
 * without a full page navigation.
 */
export default function DocumentsClient() {
  const router = useRouter();
  const [successBanner, setSuccessBanner] = useState<UploadResult | null>(null);

  function handleSuccess(result: UploadResult) {
    setSuccessBanner(result);
    // Re-run the Server Component to show the new invoice in the list
    router.refresh();
    setTimeout(() => setSuccessBanner(null), 6000);
  }

  return (
    <div className="space-y-3">
      <UploadForm onSuccess={handleSuccess} />

      {successBanner && (
        <div className="flex items-start gap-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-400">
          <span className="text-base leading-none mt-0.5">✓</span>
          <div>
            <p className="font-medium">Document envoyé avec succès</p>
            <p className="text-xs mt-0.5 text-emerald-600 dark:text-emerald-500">
              Traitement en cours — job{" "}
              <code className="font-mono">{successBanner.job_id.slice(0, 8)}…</code>
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
