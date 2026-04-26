"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";

interface Org {
  id: string;
  name: string;
  siren: string;
  role: string;
}

const ROLE_SHORT: Record<string, string> = {
  org_owner: "Propriétaire",
  org_admin: "Admin",
  accountant: "Comptable",
  auditor: "Auditeur",
  ledgermind_staff: "Staff",
};

const NAV_ITEMS = [
  { label: "Tableau de bord",   href: "/app/dashboard",            icon: "⊞" },
  { label: "Documents",         href: "/app/documents",            icon: "⊡" },
  { label: "Factures",          href: "/app/invoices",             icon: "🧾" },
  { label: "Écritures",         href: "/app/ledger",               icon: "≡" },
  { label: "Plan de comptes",   href: "/app/ledger/plan-comptes",  icon: "≔" },
  { label: "Lettrage",          href: "/app/ledger/lettrage",      icon: "⊕" },
  { label: "Rapprochement",     href: "/app/bank",                 icon: "⇌" },
  { label: "Rapports",          href: "/app/reports",              icon: "◫" },
  { label: "Exports comptables",href: "/app/ledger/exports",       icon: "↓" },
  { label: "Conformité",        href: "/app/compliance",           icon: "✓" },
];

export default function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [activeOrg, setActiveOrg] = useState<Org | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [switcherOpen, setSwitcherOpen] = useState(false);

  // Load orgs + detect active org from cookie
  useEffect(() => {
    fetch("/api/organizations")
      .then((r) => r.json())
      .then((data: { results?: Org[] } | Org[]) => {
        const list = Array.isArray(data) ? data : (data.results ?? []);
        setOrgs(list);

        // Read active_org_id cookie
        const activeCookieId = document.cookie
          .split("; ")
          .find((row) => row.startsWith("active_org_id="))
          ?.split("=")[1];

        const found = list.find((o) => o.id === activeCookieId) ?? list[0] ?? null;
        setActiveOrg(found);
      })
      .catch(() => {});
  }, []);

  async function handleLogout() {
    await fetch("/api/auth/session", { method: "DELETE" });
    await fetch("/api/org/switch", { method: "DELETE" });
    router.push("/login");
  }

  async function switchOrg(org: Org) {
    setSwitcherOpen(false);
    await fetch("/api/org/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ orgId: org.id }),
    });
    setActiveOrg(org);
    router.push("/app/dashboard");
    router.refresh();
  }

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
      {/* Logo */}
      <div className="flex h-14 items-center px-5 border-b border-zinc-200 dark:border-zinc-800">
        <span className="font-bold text-zinc-900 dark:text-zinc-50 tracking-tight">
          LedgerMind
        </span>
      </div>

      {/* Org switcher */}
      <div className="relative px-3 py-3 border-b border-zinc-100 dark:border-zinc-800">
        <button
          onClick={() => setSwitcherOpen((v) => !v)}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors"
        >
          {/* Avatar initiales */}
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-zinc-200 dark:bg-zinc-700 text-xs font-bold text-zinc-700 dark:text-zinc-200">
            {activeOrg
              ? activeOrg.name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase()
              : "—"}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-zinc-900 dark:text-zinc-50">
              {activeOrg?.name ?? "Aucun dossier"}
            </p>
            {activeOrg && (
              <p className="truncate text-[10px] text-zinc-400 dark:text-zinc-500">
                {ROLE_SHORT[activeOrg.role] ?? activeOrg.role}
              </p>
            )}
          </div>
          {orgs.length > 1 && (
            <span className="text-zinc-400 dark:text-zinc-500 text-xs shrink-0">
              {switcherOpen ? "▲" : "▼"}
            </span>
          )}
        </button>

        {/* Dropdown orgs */}
        {switcherOpen && orgs.length > 1 && (
          <div className="absolute left-3 right-3 top-full mt-1 z-50 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-lg py-1">
            {orgs.map((org) => (
              <button
                key={org.id}
                onClick={() => void switchOrg(org)}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors ${
                  org.id === activeOrg?.id ? "opacity-50 cursor-default" : ""
                }`}
                disabled={org.id === activeOrg?.id}
              >
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-zinc-200 dark:bg-zinc-700 text-[10px] font-bold text-zinc-700 dark:text-zinc-200">
                  {org.name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-xs font-medium text-zinc-900 dark:text-zinc-50">
                    {org.name}
                  </p>
                  <p className="text-[10px] text-zinc-400 font-mono">{org.siren}</p>
                </div>
                {org.id === activeOrg?.id && (
                  <span className="ml-auto text-emerald-500 text-xs">✓</span>
                )}
              </button>
            ))}
            <div className="border-t border-zinc-100 dark:border-zinc-800 mt-1 pt-1">
              <Link
                href="/app"
                onClick={() => setSwitcherOpen(false)}
                className="flex w-full items-center gap-2 px-3 py-2 text-xs text-zinc-500 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
              >
                <span>⊞</span> Tous les dossiers
              </Link>
            </div>
          </div>
        )}
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
