import assert from "node:assert/strict";
import test from "node:test";
import {
  filterNavGroupsForRole,
  findActiveNavItem,
  getUserMenuAdminItems,
  navItems,
} from "@/components/layout/nav-config";

test("findActiveNavItem matches exact routes", () => {
  const item = findActiveNavItem("/runs");

  assert.equal(item?.href, "/runs");
  assert.equal(item?.label, "Runs");
});

test("findActiveNavItem prefers the longest matching prefix", () => {
  const item = findActiveNavItem("/pack-runs/run_123");

  assert.equal(item?.href, "/pack-runs");
  assert.equal(item?.label, "Pack Runs");
});

test("findActiveNavItem returns null for unknown routes", () => {
  assert.equal(findActiveNavItem("/missing"), null);
});

test("navItems expose stable sidebar metadata", () => {
  assert.ok(navItems.length >= 8);
  assert.ok(navItems.every((item) => item.href.startsWith("/")));
  assert.ok(navItems.every((item) => item.label.trim().length > 0));
  assert.ok(navItems.every((item) => item.description.trim().length > 0));
  assert.equal(navItems[0]?.href, "/dashboard");
  assert.ok(navItems.some((item) => item.href === "/admin/providers"));
});

test("nav hides admin section for non-admin roles", () => {
  const viewerGroups = filterNavGroupsForRole("viewer");

  assert.equal(viewerGroups.some((group) => group.href === "/admin"), false);
  assert.equal(viewerGroups.some((group) => group.href === "/ai-scenarios"), false);
  assert.equal(viewerGroups.some((group) => group.href === "/settings"), false);
  const runsGroup = viewerGroups.find((group) => group.href === "/runs");
  assert.equal(runsGroup?.children?.some((item) => item.href === "/playground"), false);
});

test("nav exposes playground under runs for editor and above", () => {
  const editorGroups = filterNavGroupsForRole("editor");
  const runsGroup = editorGroups.find((group) => group.href === "/runs");

  assert.equal(runsGroup?.children?.some((item) => item.href === "/playground"), true);
});

test("sidebar hides admin and settings sections even for admin roles", () => {
  const adminGroups = filterNavGroupsForRole("admin");

  assert.equal(adminGroups.some((group) => group.href === "/admin"), false);
  assert.equal(adminGroups.some((group) => group.href === "/settings"), false);
});

test("user menu surfaces admin console and settings for tenant admins", () => {
  assert.deepEqual(
    getUserMenuAdminItems("admin").map((item) => item.href),
    ["/settings", "/audit", "/admin"]
  );
});

test("user menu surfaces admin console and settings for platform admins", () => {
  assert.deepEqual(
    getUserMenuAdminItems("system_admin").map((item) => item.href),
    ["/settings", "/audit", "/admin"]
  );
});
