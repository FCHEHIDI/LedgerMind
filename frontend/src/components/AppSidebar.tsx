"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRouter } from "next/navigation";

const NAV_ITEMS = [
  { label: "Tableau de bord", href: "/app/dashboard", icon: "⊞" },
  { label: "Écritures", href: "/app/ledger", icon: "≡" },
  { label: "Plan de comptes", href: "/app/ledger/plan-comptes", icon: "≔" },
  { label: "Exports comptables", href: "/app/ledger/exports", icon: "↓" },
  { label: "Rapports", href: "/app/reports", icon: "◫" },
  { label: "Rapprochement", href: "/app/bank", icon: "⇌" },
  { label: "Lettrage", href: "/app/ledger/lettrage", icon: "⊕" },
  { label: "Documents", href: "/app/documents", icon: "⊡" },
  { label: "Conformité", href: "/app/compliance", icon: "✓" },
];

export default function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();

  async function handleLogout() {
    await fetch("/api/auth/session", { method: "DELETE" });
    router.push("/login");
  }

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
      {/* Logo */}
      <div className="flex h-14 items-center px-5 border-b border-zinc-200 dark:border-zinc-800">
        <span className="font-bold text-zinc-900 dark:text-zinc-50 tracking-tight">
          LedgerMind
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 px-3 py-4">
        {NAV_ITEMS.map(({ label, href, icon }) => {
          const active =
            href === "/app/ledger"
              ? pathname === "/app/ledger" || (pathname.startsWith("/app/ledger/") && !pathname.startsWith("/app/ledger/lettrage") && !pathname.startsWith("/app/ledger/exports") && !pathname.startsWith("/app/ledger/plan-comptes"))
              : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                active
                  ? "bg-zinc-100 dark:bg-zinc-800 font-medium text-zinc-900 dark:text-zinc-50"
                  : "text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 hover:text-zinc-900 dark:hover:text-zinc-50"
              }`}
            >
              <span className="text-base leading-none">{icon}</span>
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Déconnexion */}
      <div className="px-3 py-4 border-t border-zinc-200 dark:border-zinc-800">
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-zinc-500 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 hover:text-zinc-900 dark:hover:text-zinc-50 transition-colors"
        >
          <span className="text-base leading-none">→</span>
          Déconnexion
        </button>
      </div>
    </aside>
  );
}
