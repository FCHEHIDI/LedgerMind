import DocumentsClient from "./DocumentsClient";

/**
 * Server Component — Documents page.
 * The invoice list, badge, and drawer are all handled client-side in DocumentsClient.
 */
export default function DocumentsPage() {
  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Documents</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
          Importez une facture PDF pour lancer le traitement automatique par les agents IA.
          Cliquez sur une facture extraite pour valider ou rejeter l&apos;écriture comptable.
        </p>
      </div>

      {/* All client-side: upload + live list + badge + drawer */}
      <DocumentsClient />
    </div>
  );
}
