export default function CompliancePage() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
      <div className="rounded-full bg-zinc-100 dark:bg-zinc-800 p-6">
        <span className="text-4xl">✓</span>
      </div>
      <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">Conformité</h1>
      <p className="text-sm text-zinc-500 dark:text-zinc-400 max-w-sm">
        Le module de conformité réglementaire (FEC DGFiP, alertes de non-conformité) est en cours
        de déploiement.
      </p>
    </div>
  );
}
