import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
      <p className="text-6xl font-bold text-zinc-200 dark:text-zinc-700">404</p>
      <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Page introuvable</h2>
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        Cette page n&apos;existe pas ou a été déplacée.
      </p>
      <Link
        href="/app/dashboard"
        className="mt-2 rounded-lg bg-zinc-900 dark:bg-zinc-50 px-4 py-2 text-sm font-medium text-white dark:text-zinc-900 hover:bg-zinc-700 dark:hover:bg-zinc-200 transition-colors"
      >
        Retour au tableau de bord
      </Link>
    </div>
  );
}
