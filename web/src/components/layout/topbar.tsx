"use client";

import { ArrowLeft, LogOut, Settings2, ShieldCheck, UserCog } from "lucide-react";
import type { Route } from "next";
import { usePathname, useRouter } from "next/navigation";
import { StatusBadge } from "@/components/ui/badge";
import { findActiveNavItem, getUserMenuAdminItems } from "@/components/layout/nav-config";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { useCurrentRole, useDashboardAccess } from "@/lib/current-user";
import { clearAuthSession, getAuthSession } from "@/lib/auth";
import { logoutAllSessions, useFeatures, useTenant } from "@/lib/api";
import {
  providerCircuitAgeLabel,
  providerCircuitBadgeVariant,
  sortProviderCircuits,
} from "@/lib/provider-circuits";
import { cn } from "@/lib/utils";

interface TopbarProps {
  title?: React.ReactNode;
  className?: string;
}

export function Topbar({
  title,
  className,
}: TopbarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: tenant } = useTenant();
  const { data: features } = useFeatures();
  const role = useCurrentRole();
  const { canViewAdminSection } = useDashboardAccess();
  const selectedTenant = getAuthSession()?.tenantName;
  const userInitial = role?.charAt(0).toUpperCase() ?? "U";
  const providerCircuits = sortProviderCircuits(features?.provider_circuits ?? []);
  const openCircuits = providerCircuits.filter((circuit) => circuit.state === "open");
  const degradedLabel =
    openCircuits.length > 0 ? `Provider degraded (${openCircuits.length})` : "Provider degraded";
  const harnessDegraded = features?.harness_degraded === true;
  const harnessState = (features?.harness_state ?? "unknown").replace("_", " ");
  const activeNavItem = findActiveNavItem(pathname);
  const effectiveTitle = title ?? activeNavItem?.label ?? "Dashboard";
  const effectiveDescription = activeNavItem?.description ?? "Operator workspace";
  const adminMenuItems = getUserMenuAdminItems(role);
  const roleLabel = role ? role.replace("_", " ") : "user";
  const tenantBadgeLabel = tenant?.name ?? selectedTenant ?? tenant?.tenant_id ?? "tenant";

  async function handleLogout() {
    try {
      await logoutAllSessions();
    } catch {
      // Local cleanup still runs so the user can re-authenticate.
    } finally {
      clearAuthSession();
      router.replace("/login" as Route);
    }
  }

  function goToUserSettings() {
    router.push("/account" as Route);
  }

  function goToRoute(href: string) {
    router.push(href as Route);
  }

  return (
    <header
      className={cn(
        "flex h-16 items-center justify-between border-b border-border bg-bg-surface/95 px-6 backdrop-blur",
        className
      )}
    >
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          aria-label="Go back"
          title="Go back"
          onClick={() => router.back()}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border bg-bg-elevated text-text-secondary transition-colors hover:border-brand hover:text-text-primary focus:outline-none focus:ring-2 focus:ring-border-focus"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-text-primary">{effectiveTitle}</div>
          <div className="truncate text-xs text-text-muted">{effectiveDescription}</div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <ThemeToggle />
        {harnessDegraded && (
          <span
            title="Harness worker degraded"
            className="inline-flex items-center rounded-md border border-fail/60 bg-fail/10 px-2.5 py-1 text-xs font-semibold text-fail"
          >
            Harness degraded ({harnessState})
          </span>
        )}
        {features?.provider_degraded && (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                title="Provider circuit degraded"
                className="inline-flex items-center rounded-md border border-warn/60 bg-warn/10 px-2.5 py-1 text-xs font-semibold text-warn transition-colors hover:border-warn hover:bg-warn/15"
              >
                {degradedLabel}
              </button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-96 space-y-2 p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-text-primary">Provider circuits</p>
                <span className="text-[11px] text-text-muted">Refreshed every 60s</span>
              </div>
              <div className="space-y-2">
                {providerCircuits.length === 0 ? (
                  <p className="rounded border border-border bg-bg-subtle px-2 py-1 text-xs text-text-muted">
                    No circuit snapshots available.
                  </p>
                ) : (
                  providerCircuits.map((circuit) => (
                    <div
                      key={`${circuit.source}:${circuit.provider}:${circuit.component}`}
                      className="rounded border border-border bg-bg-subtle px-2 py-1.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-xs font-medium text-text-primary">
                            {circuit.source}:{circuit.component}
                          </p>
                          <p className="text-[11px] text-text-muted">
                            {circuit.provider} / {circuit.service}
                          </p>
                        </div>
                        <StatusBadge
                          value={providerCircuitBadgeVariant(circuit.state)}
                          label={circuit.state.replace("_", " ")}
                          className="uppercase"
                        />
                      </div>
                      <p className="mt-1 text-[11px] text-text-muted">
                        Last update: {providerCircuitAgeLabel(circuit.updated_at)}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </PopoverContent>
          </Popover>
        )}
        <span className="inline-flex items-center rounded-md border border-info-border bg-brand-muted px-2.5 py-1 text-xs font-mono text-info">
          {tenantBadgeLabel}
        </span>
        {role ? (
          <span className="inline-flex items-center rounded-md border border-border bg-bg-elevated px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
            {roleLabel}
          </span>
        ) : null}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label="Open account menu"
              className="flex h-9 w-9 items-center justify-center rounded-full border border-info-border bg-gradient-to-br from-brand/30 to-brand-muted text-sm font-semibold text-brand shadow-sm transition hover:scale-[1.03] hover:border-brand focus:outline-none focus:ring-2 focus:ring-brand/50"
            >
              {userInitial}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-72 rounded-xl p-2">
            <DropdownMenuLabel className="px-2 py-2">
              <div className="space-y-1">
                <p className="text-sm font-semibold text-text-primary">Account</p>
                <p className="text-xs text-text-muted">
                  {tenantBadgeLabel} · {roleLabel}
                </p>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="items-start gap-3 rounded-lg px-3 py-2.5" onSelect={goToUserSettings}>
              <UserCog className="mt-0.5 h-4 w-4 text-text-muted" />
              <div className="min-w-0">
                <div className="text-sm font-medium text-text-primary">User Settings</div>
                <div className="text-xs text-text-muted">Security, password, and TOTP management.</div>
              </div>
            </DropdownMenuItem>
            {canViewAdminSection ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-text-muted">
                  Administration
                </DropdownMenuLabel>
                {adminMenuItems.map((item) => {
                  const Icon =
                    item.href === "/settings"
                      ? Settings2
                      : item.href === "/admin"
                        ? ShieldCheck
                        : item.icon;
                  return (
                    <DropdownMenuItem
                      key={item.href}
                      className="items-start gap-3 rounded-lg px-3 py-2.5"
                      onSelect={() => goToRoute(item.href)}
                    >
                      <Icon className="mt-0.5 h-4 w-4 text-text-muted" />
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-text-primary">{item.label}</div>
                        <div className="text-xs text-text-muted">{item.description}</div>
                      </div>
                    </DropdownMenuItem>
                  );
                })}
              </>
            ) : null}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="items-start gap-3 rounded-lg px-3 py-2.5 text-fail focus:text-fail"
              onSelect={() => {
                void handleLogout();
              }}
            >
              <LogOut className="mt-0.5 h-4 w-4" />
              <div className="min-w-0">
                <div className="text-sm font-medium">Logout</div>
                <div className="text-xs text-text-muted">End this session on this device.</div>
              </div>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
