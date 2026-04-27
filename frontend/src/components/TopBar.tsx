"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Search, Bell, HelpCircle } from "lucide-react";

const BREADCRUMB: Record<string, string> = {
  "/app/dashboard":           "Tableau de bord",
  "/app/documents":           "Documents",
  "/app/invoices":            "Factures",
  "/app/ledger":              "Écritures",
  "/app/ledger/plan-comptes": "Plan de comptes",
  "/app/ledger/lettrage":     "Lettrage",
  "/app/ledger/exports":      "Exports comptables",
  "/app/ledger/new":          "Nouvelle écriture",
  "/app/bank":                "Rapprochement bancaire",
  "/app/reports":             "Rapports financiers",
  "/app/compliance":          "Conformité",
};

function getBreadcrumb(pathname: string): string {
  if (BREADCRUMB[pathname]) return BREADCRUMB[pathname];
  // match prefixes longest first
  const sorted = Object.keys(BREADCRUMB).sort((a, b) => b.length - a.length);
  for (const key of sorted) {
    if (pathname.startsWith(key)) return BREADCRUMB[key];
  }
  return "LedgerMind";
}

export default function TopBar() {
  const pathname = usePathname();
  const [searchFocused, setSearchFocused] = useState(false);

  return (
    <header
      style={{
        height: "var(--topbar-h)",
        background: "var(--bg-card)",
        borderBottom: "1px solid var(--border)",
        boxShadow: "var(--shadow-xs)",
      }}
      className="flex items-center justify-between px-6 shrink-0 gap-4"
    >
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-xs" style={{ color: "var(--text-tertiary)" }}>
          LedgerMind
        </span>
        <span style={{ color: "var(--border)" }}>/</span>
        <span className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
          {getBreadcrumb(pathname)}
        </span>
      </div>

      {/* Search + Actions */}
      <div className="flex items-center gap-2 shrink-0">
        {/* Search bar */}
        <div
          className="flex items-center gap-2 rounded-lg px-3 py-1.5 transition-all"
          style={{
            background: "var(--bg-root)",
            border: `1px solid ${searchFocused ? "var(--amber-400)" : "var(--border)"}`,
            boxShadow: searchFocused ? "0 0 0 3px rgba(245,158,11,0.12)" : "none",
            width: searchFocused ? "240px" : "200px",
          }}
        >
          <Search size={13} style={{ color: "var(--text-tertiary)" }} className="shrink-0" />
          <input
            type="text"
            placeholder="Rechercher…"
            className="bg-transparent text-xs outline-none flex-1 min-w-0"
            style={{ color: "var(--text-primary)" }}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
          />
          <kbd
            className="text-[10px] px-1.5 py-0.5 rounded font-mono"
            style={{
              background: "var(--border-light)",
              color: "var(--text-tertiary)",
              border: "1px solid var(--border)",
            }}
          >
            ⌘K
          </kbd>
        </div>

        {/* Icon actions */}
        <button
          className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
          style={{ color: "var(--text-secondary)" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "var(--bg-root)";
            e.currentTarget.style.color = "var(--text-primary)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.color = "var(--text-secondary)";
          }}
          title="Aide"
        >
          <HelpCircle size={16} />
        </button>

        <button
          className="relative flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
          style={{ color: "var(--text-secondary)" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "var(--bg-root)";
            e.currentTarget.style.color = "var(--text-primary)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.color = "var(--text-secondary)";
          }}
          title="Notifications"
        >
          <Bell size={16} />
          {/* Notification dot */}
          <span
            className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full"
            style={{ background: "var(--amber-500)" }}
          />
        </button>
      </div>
    </header>
  );
}
