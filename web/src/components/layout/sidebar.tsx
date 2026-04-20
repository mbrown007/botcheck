"use client";

import Image from "next/image";
import Link from "next/link";
import type { Route } from "next";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { filterNavGroupsForRole, type NavItem } from "@/components/layout/nav-config";
import { useCurrentRole } from "@/lib/current-user";
import { useTenant } from "@/lib/api";
import { cn } from "@/lib/utils";

interface SidebarProps {
  collapsed: boolean;
  onToggle?: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const { data: tenant } = useTenant();
  const role = useCurrentRole();
  const tenantLabel = tenant?.tenant_id ?? "tenant";
  const { resolvedTheme } = useTheme();
  const isLight = resolvedTheme === "light";
  const navGroups = filterNavGroupsForRole(role);

  return (
    <aside
      className={cn(
        "flex h-screen shrink-0 flex-col border-r border-border bg-bg-surface transition-[width] duration-200 ease-out",
        collapsed ? "w-[86px]" : "w-[248px]"
      )}
    >
      <div className={cn("border-b border-border", collapsed ? "px-3 py-4" : "px-4 py-4")}>
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="block w-full focus:outline-none focus:ring-2 focus:ring-border-focus rounded-md"
        >
          {collapsed ? (
            <Image
              src={isLight ? "/icon-lightmode.png" : "/darkmode-icon.png"}
              alt="BotCheck"
              width={120}
              height={120}
              priority
              className="mx-auto h-12 w-12 object-contain"
            />
          ) : (
            <Image
              src={isLight ? "/logo-lightmode.png" : "/graibot.png"}
              alt="BotCheck"
              width={895}
              height={265}
              priority
              className="h-auto w-full object-contain"
            />
          )}
        </button>
      </div>

      <TooltipProvider delayDuration={120}>
        <nav className={cn("flex-1 overflow-y-auto py-4", collapsed ? "px-2" : "px-3")}>
          <div className="space-y-1">
            {navGroups.map((group) => {
              const groupActive =
                pathname === group.href || pathname.startsWith(`${group.href}/`);
              return (
                <div key={group.href} className="space-y-1">
                  {renderNavItem({
                    item: group,
                    pathname,
                    collapsed,
                    nested: false,
                  })}
                  {!collapsed && groupActive && group.children?.length ? (
                    <div className="space-y-1 pl-5">
                      {group.children.map((child) =>
                        renderNavItem({
                          item: child,
                          pathname,
                          collapsed,
                          nested: true,
                          forceExpanded: true,
                        })
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </nav>
      </TooltipProvider>

      <div className={cn("border-t border-border", collapsed ? "px-2 py-3" : "px-4 py-4")}>
        {collapsed ? (
          <TooltipProvider delayDuration={120}>
            <div className="space-y-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Link
                    href={"/docs" as Route}
                    className="flex h-10 items-center justify-center rounded-xl border border-border bg-bg-elevated text-xs text-text-secondary transition-colors hover:text-text-primary"
                    aria-label="Documentation"
                  >
                    Docs
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right">Documentation</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex h-10 items-center justify-center rounded-xl border border-border bg-bg-elevated px-2 text-[10px] font-mono text-text-muted">
                    {tenantLabel.slice(0, 4)}
                  </div>
                </TooltipTrigger>
                <TooltipContent side="right">{tenantLabel}</TooltipContent>
              </Tooltip>
            </div>
          </TooltipProvider>
        ) : (
          <div className="space-y-3">
            <Link
              href={"/docs" as Route}
              className="block text-xs text-text-muted transition-colors hover:text-text-secondary"
            >
              Documentation
            </Link>
            <div className="inline-flex items-center rounded-md border border-border bg-bg-elevated px-2 py-1 text-xs font-mono text-text-muted">
              {tenantLabel}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

function renderNavItem({
  item,
  pathname,
  collapsed,
  nested,
  forceExpanded = false,
}: {
  item: NavItem;
  pathname: string;
  collapsed: boolean;
  nested: boolean;
  forceExpanded?: boolean;
}) {
  const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
  const Icon = item.icon;
  const link = (
    <Link
      href={item.href as Route}
      aria-label={collapsed ? item.label : undefined}
      className={cn(
        "group flex items-center rounded-xl transition-all duration-150",
        collapsed ? "justify-center px-0 py-3" : "gap-3 px-3 py-2.5",
        nested && !collapsed && "border-l border-border/70 rounded-l-none pl-4",
        active
          ? "bg-brand-muted text-brand shadow-sm ring-1 ring-brand/10"
          : "text-text-secondary hover:bg-bg-elevated hover:text-text-primary",
        forceExpanded && nested && !active && "bg-bg-base/50"
      )}
    >
      <Icon
        className={cn(
          "h-4 w-4 shrink-0",
          active ? "text-brand" : "text-text-muted group-hover:text-text-primary"
        )}
      />
      {!collapsed && (
        <div className="min-w-0">
          <div className={cn("truncate font-medium", nested ? "text-[13px]" : "text-sm")}>
            {item.label}
          </div>
          <div className="truncate text-[11px] text-text-muted">{item.description}</div>
        </div>
      )}
    </Link>
  );

  if (!collapsed) {
    return <div key={item.href}>{link}</div>;
  }

  return (
    <Tooltip key={item.href}>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">
        <div className="space-y-0.5">
          <p className="font-medium">{item.label}</p>
          <p className="max-w-[220px] text-[11px] text-text-muted">{item.description}</p>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
