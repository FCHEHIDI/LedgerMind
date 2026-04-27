import type { ReactNode } from "react";
import AppSidebar from "@/components/AppSidebar";
import TopBar from "@/components/TopBar";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: "var(--bg-root)" }}
    >
      <AppSidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
