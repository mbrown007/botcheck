import assert from "node:assert/strict";
import test from "node:test";
import { getDashboardAccess, hasMinimumRole, normalizeRole } from "@/lib/rbac";

test("normalizeRole accepts only canonical API roles", () => {
  assert.equal(normalizeRole("viewer"), "viewer");
  assert.equal(normalizeRole("system_admin"), "system_admin");
  assert.equal(normalizeRole("owner"), null);
  assert.equal(normalizeRole(""), null);
});

test("hasMinimumRole follows the API rank order", () => {
  assert.equal(hasMinimumRole("viewer", "viewer"), true);
  assert.equal(hasMinimumRole("viewer", "operator"), false);
  assert.equal(hasMinimumRole("operator", "viewer"), true);
  assert.equal(hasMinimumRole("editor", "operator"), true);
  assert.equal(hasMinimumRole("admin", "editor"), true);
  assert.equal(hasMinimumRole("system_admin", "admin"), true);
});

test("viewer access is read-only and hides admin surfaces", () => {
  const access = getDashboardAccess("viewer");

  assert.equal(access.canManageScenarios, false);
  assert.equal(access.canOperateRuns, false);
  assert.equal(access.canManageSchedules, false);
  assert.equal(access.canUsePlayground, false);
  assert.equal(access.canViewAdminSection, false);
});

test("operator access enables run controls but not editor surfaces", () => {
  const access = getDashboardAccess("operator");

  assert.equal(access.canOperateRuns, true);
  assert.equal(access.canManageScenarios, false);
  assert.equal(access.canManageSchedules, false);
  assert.equal(access.canUseBuilder, false);
});

test("editor access enables graph authoring but not admin surfaces", () => {
  const access = getDashboardAccess("editor");

  assert.equal(access.canManageScenarios, true);
  assert.equal(access.canManageSchedules, true);
  assert.equal(access.canUseBuilder, true);
  assert.equal(access.canUsePlayground, true);
  assert.equal(access.canViewAdminSection, false);
});

test("tenant admin access enables tenant admin pages but not platform pages", () => {
  const access = getDashboardAccess("admin");

  assert.equal(access.canViewAdminSection, true);
  assert.equal(access.canAccessAdminUsers, true);
  assert.equal(access.canAccessAdminAudit, true);
  assert.equal(access.canAccessAdminTenants, false);
  assert.equal(access.canAccessAdminSystem, false);
  assert.equal(access.canManageAIScenarios, true);
});

test("platform admin access enables every admin surface", () => {
  const access = getDashboardAccess("system_admin");

  assert.equal(access.canAccessAdminUsers, true);
  assert.equal(access.canAccessAdminAudit, true);
  assert.equal(access.canAccessAdminTenants, true);
  assert.equal(access.canAccessAdminSip, true);
  assert.equal(access.canAccessAdminSystem, true);
});
