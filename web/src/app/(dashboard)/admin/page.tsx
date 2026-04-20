"use client";

import Link from "next/link";
import type { Route } from "next";
import { AccessPanel } from "@/components/auth/access-panel";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { useDashboardAccess } from "@/lib/current-user";

function AdminLinkCard({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link href={href as Route} className="block">
      <Card className="h-full transition-colors hover:border-brand/40 hover:bg-bg-elevated">
        <CardHeader>
          <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
        </CardHeader>
        <CardBody>
          <p className="text-sm text-text-secondary">{description}</p>
        </CardBody>
      </Card>
    </Link>
  );
}

export default function AdminOverviewPage() {
  const {
    roleResolved,
    canViewAdminSection,
    canAccessAdminSip,
    canAccessAdminProviders,
    canAccessAdminSystem,
    canAccessAdminTenants,
    canAccessAdminUsers,
  } = useDashboardAccess();

  if (!roleResolved) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-text-muted">Loading admin capabilities…</p>
        </CardBody>
      </Card>
    );
  }

  if (!canViewAdminSection) {
    return (
      <AccessPanel
        title="Admin"
        message="The admin control plane is restricted to admin role or above."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Admin</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Tenant-scoped administration and platform control-plane surfaces. Use the main Audit
          page for activity history.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {canAccessAdminUsers ? (
          <AdminLinkCard
            href="/admin/users"
            title="User Admin"
            description="Create tenant users, revoke sessions, and run recovery actions."
          />
        ) : null}
        {canAccessAdminTenants ? (
          <AdminLinkCard
            href="/admin/tenants"
            title="Tenant Admin"
            description="Manage tenants, overrides, suspension state, and quotas."
          />
        ) : null}
        {canAccessAdminProviders ? (
          <AdminLinkCard
            href="/admin/providers"
            title="Provider Admin"
            description="Manage platform credentials, tenant assignments, and provider readiness."
          />
        ) : null}
        {canAccessAdminSystem ? (
          <AdminLinkCard
            href="/admin/system"
            title="System Admin"
            description="Inspect platform health, defaults, and redacted runtime config."
          />
        ) : null}
        {canAccessAdminSip ? (
          <AdminLinkCard
            href="/admin/sip"
            title="SIP Admin"
            description="Inspect SIP trunks and trigger registry sync."
          />
        ) : null}
      </div>
    </div>
  );
}
