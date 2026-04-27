"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import {
  LayoutDashboard,
  FileText,
  Receipt,
  BookOpen,
  List,
  GitMerge,
  Landmark,
  BarChart2,
  Download,
  ShieldCheck,
  ChevronsUpDown,
  Check,
  LogOut,
  Upload,
  Building2,
  type LucideIcon,
} from "lucide-react";

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

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  exact?: boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Vue d'ensemble",
    items: [
      { label: "Tableau de bord", href: "/app/dashboard", icon: LayoutDashboard },
      { label: "Documents",       href: "/app/documents", icon: FileText },
      { label: "Factures",        href: "/app/invoices",  icon: Receipt },
    ],
  },
  {
    label: "Comptabilité",
    items: [
      { label: "Écritures",        href: "/app/ledger",              icon: BookOpen, exact: true },
      { label: "Plan de comptes",  href: "/app/ledger/plan-comptes", icon: List },
      { label: "Lettrage",         href: "/app/ledger/lettrage",     icon: GitMerge },
    ],
  },
  {
    label: "Analyse",
    items: [
      { label: "Rapprochement",     href: "/app/bank",            icon: Landmark },
      { label: "Rapports",          href: "/app/reports",         icon: BarChart2 },
      { label: "Exports comptables",href: "/app/ledger/exports",  icon: Download },
      { label: "Conformité",        href: "/app/compliance",      icon: ShieldCheck },
    ],
  },
];

function OrgInitials({ name }: { name: string }) {
  const initials = name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
  return (
    <div
      style={{ background: "var(--amber-600)", color: "#fff" }}
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[11px] font-bold"
    >
      {initials}
    </div>
  );
}

export default function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [activeOrg, setActiveOrg] = useState<Org | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [switcherOpen, setSwitcherOpen] = useState(false);

  useEffect(() => {
    fetch("/api/organizations")
      .then((r) => r.json())
      .then((data: { results?: Org[] } | Org[]) => {
        const list = Array.isArray(data) ? data : (data.results ?? []);
        setOrgs(list);
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

  function isActive(item: NavItem): boolean {
    if (item.exact) return pathname === item.href;
    return pathname.startsWith(item.href);
  }

  return (
    <aside
      style={{
        width: "var(--sidebar-w)",
        background: "var(--bg-sidebar)",
        borderRight: "1px solid var(--border-sidebar)",
      }}
      className="flex shrink-0 flex-col h-full"
    >
      {/* ── Logo ── */}
      <div
        style={{ height: "var(--topbar-h)", borderBottom: "1px solid var(--border-sidebar)" }}
        className="flex items-center gap-2.5 px-5"
      >
        {/* Icon mark */}
        <div
          style={{ background: "var(--amber-500)", borderRadius: "8px" }}
          className="flex h-7 w-7 items-center justify-center shrink-0"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 4h10M3 8h7M3 12h5" stroke="#131110" strokeWidth="2" strokeLinecap="round"/>
          </svg>
        </div>
        <span className="text-sm font-semibold tracking-tight" style={{ color: "var(--text-light)" }}>
          <span style={{ color: "var(--amber-400)" }}>Ledger</span>Mind
        </span>
      </div>

      {/* ── Org switcher ── */}
      <div
        style={{ borderBottom: "1px solid var(--border-sidebar)" }}
        className="relative px-3 py-2.5"
      >
        <button
          onClick={() => setSwitcherOpen((v) => !v)}
          className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors"
          style={{ background: "transparent" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-sidebar-hover)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          {activeOrg ? <OrgInitials name={activeOrg.name} /> : (
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
              style={{ background: "rgba(255,255,255,0.08)" }}>
              <Building2 size={13} style={{ color: "var(--text-light-muted)" }} />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium" style={{ color: "var(--text-light)" }}>
              {activeOrg?.name ?? "Aucun dossier"}
            </p>
            {activeOrg && (
              <p className="truncate text-[10px]" style={{ color: "var(--text-light-muted)" }}>
                {ROLE_SHORT[activeOrg.role] ?? activeOrg.role}
              </p>
            )}
          </div>
          {orgs.length > 1 && (
            <ChevronsUpDown size={12} style={{ color: "var(--text-light-muted)" }} className="shrink-0" />
          )}
        </button>

        {/* Dropdown */}
        {switcherOpen && orgs.length > 1 && (
          <div
            className="absolute left-3 right-3 top-full mt-1 z-50 rounded-xl py-1 shadow-lg"
            style={{
              background: "#1C1917",
              border: "1px solid var(--border-sidebar)",
              boxShadow: "var(--shadow-md)",
            }}
          >
            {orgs.map((org) => (
              <button
                key={org.id}
                onClick={() => void switchOrg(org)}
                disabled={org.id === activeOrg?.id}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors"
                style={{ opacity: org.id === activeOrg?.id ? 0.5 : 1 }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-sidebar-hover)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <OrgInitials name={org.name} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium" style={{ color: "var(--text-light)" }}>
                    {org.name}
                  </p>
                  <p className="text-[10px] font-mono" style={{ color: "var(--text-light-muted)" }}>
                    {org.siren}
                  </p>
                </div>
                {org.id === activeOrg?.id && (
                  <Check size={12} style={{ color: "var(--amber-500)" }} className="shrink-0" />
                )}
              </button>
            ))}
            <div style={{ borderTop: "1px solid var(--border-sidebar)" }} className="mt-1 pt-1">
              <Link
                href="/app"
                onClick={() => setSwitcherOpen(false)}
                className="flex w-full items-center gap-2 px-3 py-2 text-xs transition-colors"
                style={{ color: "var(--text-light-muted)" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-light)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-light-muted)")}
              >
                <Building2 size={12} />
                Tous les dossiers
              </Link>
            </div>
          </div>
        )}
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <p
              className="px-2 mb-1.5 text-[10px] font-semibold uppercase tracking-widest"
              style={{ color: "var(--text-light-muted)" }}
            >
              {group.label}
            </p>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active = isActive(item);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-all"
                    style={{
                      background: active ? "var(--bg-sidebar-active)" : "transparent",
                      color: active ? "var(--amber-400)" : "var(--text-light-muted)",
                      fontWeight: active ? "500" : "400",
                    }}
                    onMouseEnter={(e) => {
                      if (!active) {
                        e.currentTarget.style.background = "var(--bg-sidebar-hover)";
                        e.currentTarget.style.color = "var(--text-light)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!active) {
                        e.currentTarget.style.background = "transparent";
                        e.currentTarget.style.color = "var(--text-light-muted)";
                      }
                    }}
                  >
                    <Icon size={15} className="shrink-0" />
                    <span className="truncate">{item.label}</span>
                    {active && (
                      <span
                        className="ml-auto h-1.5 w-1.5 rounded-full shrink-0"
                        style={{ background: "var(--amber-500)" }}
                      />
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* ── Quick upload CTA ── */}
      <div className="px-3 pb-3">
        <div
          className="rounded-xl p-3"
          style={{ background: "var(--bg-sidebar-active)", border: "1px dashed rgba(245,158,11,0.3)" }}
        >
          <p className="text-[11px] font-medium mb-2" style={{ color: "var(--amber-400)" }}>
            Import rapide
          </p>
          <p className="text-[10px] mb-3" style={{ color: "var(--text-light-muted)" }}>
            Glissez un document ou cliquez pour analyser
          </p>
          <Link
            href="/app/documents"
            className="flex items-center justify-center gap-1.5 w-full rounded-lg py-1.5 text-xs font-medium transition-colors"
            style={{ background: "var(--amber-600)", color: "#fff" }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--amber-700)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "var(--amber-600)")}
          >
            <Upload size={12} />
            Importer
          </Link>
        </div>
      </div>

      {/* ── User footer ── */}
      <div
        style={{ borderTop: "1px solid var(--border-sidebar)" }}
        className="px-3 py-3"
      >
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors"
          style={{ color: "var(--text-light-muted)" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "#ef4444";
            e.currentTarget.style.background = "rgba(239,68,68,0.08)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "var(--text-light-muted)";
            e.currentTarget.style.background = "transparent";
          }}
        >
          <LogOut size={14} className="shrink-0" />
          Déconnexion
        </button>
      </div>
    </aside>
  );
}
