"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { useCurrentUser } from "@/lib/api";
import { readSidebarPrefs, writeSidebarPrefs } from "@/lib/sidebar-state";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  useCurrentUser();

  useEffect(() => {
    const persisted = readSidebarPrefs();
    if (persisted) {
      setSidebarCollapsed(persisted.collapsed);
    }
  }, []);

  useEffect(() => {
    writeSidebarPrefs({ collapsed: sidebarCollapsed });
  }, [sidebarCollapsed]);

  return (
    <div className="flex h-screen overflow-hidden bg-bg-base">
      <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((c) => !c)} />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-y-auto bg-bg-base px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
