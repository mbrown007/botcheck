"use client";

import { UserSecurityPanel } from "@/components/settings/user-security-panel";

export default function AccountPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">User Settings</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Manage security controls for your account.
        </p>
      </div>
      <UserSecurityPanel />
    </div>
  );
}
