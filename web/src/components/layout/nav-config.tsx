import type { LucideIcon } from "lucide-react";
import {
  Building2,
  Boxes,
  CalendarClock,
  ClipboardList,
  FileSearch,
  FlaskConical,
  KeyRound,
  LayoutDashboard,
  LayoutTemplate,
  Route,
  ScanSearch,
  Settings2,
  Shield,
  ShieldCheck,
  ServerCog,
  Voicemail,
  TestTubeDiagonal,
  UsersRound,
} from "lucide-react";
import { hasMinimumRole, isPlatformAdmin, type AppRole } from "@/lib/rbac";

export interface NavItem {
  href: string;
  label: string;
  shortLabel: string;
  description: string;
  icon: LucideIcon;
  minimumRole?: AppRole;
  platformAdminOnly?: boolean;
  sidebarVisible?: boolean;
}

export interface NavGroup extends NavItem {
  children?: NavItem[];
}

export const navGroups: NavGroup[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    shortLabel: "Dashboard",
    description: "Tenant pulse, schedule risk, usage headroom, and platform readiness.",
    icon: LayoutDashboard,
  },
  {
    href: "/scenarios",
    label: "Scenarios",
    shortLabel: "Scenarios",
    description: "Graph and runtime-backed scenario definitions.",
    icon: ClipboardList,
    children: [
      {
        href: "/builder",
        label: "Scenario Builder",
        shortLabel: "Builder",
        description: "Visual flow editor for graph scenarios.",
        icon: Route,
        minimumRole: "editor",
      },
    ],
  },
  {
    href: "/ai-scenarios",
    label: "AI Scenarios",
    shortLabel: "AI",
    description: "Intent-first AI caller scenarios, personas, and records.",
    icon: ScanSearch,
    minimumRole: "admin",
    children: [
      {
        href: "/personas",
        label: "Personas",
        shortLabel: "Personas",
        description: "Reusable caller identities with portraits, tone, and backstory.",
        icon: UsersRound,
        minimumRole: "admin",
      },
    ],
  },
  {
    href: "/admin",
    label: "Admin",
    shortLabel: "Admin",
    description: "Tenant and platform administration surfaces.",
    icon: ShieldCheck,
    minimumRole: "admin",
    sidebarVisible: false,
    children: [
      {
        href: "/admin/users",
        label: "User Admin",
        shortLabel: "Users",
        description: "Manage tenant users, sessions, and recovery actions.",
        icon: UsersRound,
        minimumRole: "admin",
      },
      {
        href: "/admin/audit",
        label: "Admin Audit",
        shortLabel: "Audit",
        description: "Legacy control-plane audit surface. Use the main audit page instead.",
        icon: Shield,
        minimumRole: "admin",
        sidebarVisible: false,
      },
      {
        href: "/admin/tenants",
        label: "Tenant Admin",
        shortLabel: "Tenants",
        description: "Platform-level tenant lifecycle, overrides, and quotas.",
        icon: Building2,
        minimumRole: "system_admin",
        platformAdminOnly: true,
      },
      {
        href: "/admin/providers",
        label: "Provider Admin",
        shortLabel: "Providers",
        description: "Provider credentials, tenant assignments, and model-level readiness.",
        icon: KeyRound,
        minimumRole: "system_admin",
        platformAdminOnly: true,
      },
      {
        href: "/admin/system",
        label: "System Admin",
        shortLabel: "System",
        description: "Platform health, defaults, and feature overrides.",
        icon: ServerCog,
        minimumRole: "system_admin",
        platformAdminOnly: true,
      },
      {
        href: "/admin/sip",
        label: "SIP Admin",
        shortLabel: "SIP",
        description: "SIP trunk inventory and sync operations.",
        icon: Voicemail,
        minimumRole: "system_admin",
        platformAdminOnly: true,
      },
    ],
  },
  {
    href: "/packs",
    label: "Packs",
    shortLabel: "Packs",
    description: "Regression packs spanning graph and AI scenarios.",
    icon: Boxes,
    children: [
      {
        href: "/pack-runs",
        label: "Pack Runs",
        shortLabel: "Pack Runs",
        description: "Aggregate execution view for pack dispatch and outcomes.",
        icon: LayoutTemplate,
      },
    ],
  },
  {
    href: "/runs",
    label: "Runs",
    shortLabel: "Runs",
    description: "Live and historical execution records.",
    icon: TestTubeDiagonal,
    children: [
      {
        href: "/playground",
        label: "Playground",
        shortLabel: "Playground",
        description: "Live mock and direct HTTP bot trials before production dispatch.",
        icon: FlaskConical,
        minimumRole: "editor",
      },
    ],
  },
  {
    href: "/grai-evals",
    label: "Grai Evals",
    shortLabel: "Evals",
    description: "Large HTTP eval suites, run progress, and failure-focused reports.",
    icon: FileSearch,
  },
  {
    href: "/schedules",
    label: "Schedules",
    shortLabel: "Schedules",
    description: "Automated dispatch, cadence, and targeting controls.",
    icon: CalendarClock,
  },
  {
    href: "/audit",
    label: "Security & Audit",
    shortLabel: "Audit",
    description: "Mutation trail, security events, and compliance evidence.",
    icon: Shield,
    sidebarVisible: false,
  },
  {
    href: "/settings",
    label: "General Settings",
    shortLabel: "Settings",
    description: "Tenant-wide configuration, destinations, and flags.",
    icon: Settings2,
    sidebarVisible: false,
  },
];

export const navItems: NavItem[] = navGroups.flatMap((group) => [group, ...(group.children ?? [])]);

export function filterNavGroupsForRole(role: string | null | undefined): NavGroup[] {
  return navGroups
    .map((group) => {
      const children = (group.children ?? []).filter(
        (child) => child.sidebarVisible !== false && canViewNavItem(child, role)
      );
      return {
        ...group,
        children,
      };
    })
    .filter(
      (group) =>
        group.sidebarVisible !== false &&
        (canViewNavItem(group, role) || (group.children?.length ?? 0) > 0)
    );
}

export function getUserMenuAdminItems(role: string | null | undefined): NavItem[] {
  return ["/settings", "/audit", "/admin"]
    .map((href) => navItems.find((item) => item.href === href) ?? null)
    .filter((item): item is NavItem => item !== null)
    .filter((item) => canViewNavItem(item, role));
}

function canViewNavItem(item: NavItem, role: string | null | undefined): boolean {
  if (item.platformAdminOnly && !isPlatformAdmin(role)) {
    return false;
  }
  return hasMinimumRole(role, item.minimumRole ?? "viewer");
}

export function findActiveNavItem(pathname: string): NavItem | null {
  const matches = navItems.filter(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`)
  );
  return matches.sort((left, right) => right.href.length - left.href.length)[0] ?? null;
}
