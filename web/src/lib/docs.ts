import { promises as fs } from "node:fs";
import path from "node:path";
import "server-only";

interface DocsPageMeta {
  slug: string[];
  title: string;
  description: string;
  section: string;
  order: number;
  file: string;
}

interface DocsSection {
  title: string;
  pages: DocsPageMeta[];
}

const DOCS_PAGES: DocsPageMeta[] = [
  {
    slug: ["getting-started"],
    title: "Getting Started",
    description: "Platform overview, first steps, and how the docs are organized.",
    section: "Introduction",
    order: 10,
    file: "getting-started.md",
  },
  {
    slug: ["platform-guide"],
    title: "Platform Guide",
    description: "Comprehensive guide to BotCheck concepts, features, and administration.",
    section: "Introduction",
    order: 15,
    file: "platform-guide.md",
  },
  {
    slug: ["scenario-builder"],
    title: "Scenario Builder",
    description: "Graph authoring workflow, runtime config, and editing model.",
    section: "Authoring",
    order: 20,
    file: "scenario-builder.md",
  },
  {
    slug: ["scenario-yaml-reference"],
    title: "Scenario YAML Reference",
    description: "Complete reference for the scenario YAML format: all fields, branching, assertions, scoring, and validation rules.",
    section: "Authoring",
    order: 25,
    file: "scenario-yaml-reference.md",
  },
  {
    slug: ["ai-scenarios"],
    title: "AI Scenarios",
    description: "Intent-first AI scenario authoring, records, and speech/runtime overrides.",
    section: "Authoring",
    order: 30,
    file: "ai-scenarios.md",
  },
  {
    slug: ["personas"],
    title: "AI Personas",
    description: "Harness behavior, mood, and voice identity for AI scenarios.",
    section: "Authoring",
    order: 35,
    file: "personas-guide.md",
  },
  {
    slug: ["playground"],
    title: "Scenario Playground",
    description: "Browser-based sandbox for running scenarios without SIP: mock agent and direct HTTP modes.",
    section: "Authoring",
    order: 38,
    file: "playground-guide.md",
  },
  {
    slug: ["runs"],
    title: "Managing Runs",
    description: "Individual scenario executions, live monitoring, and judge reports.",
    section: "Operations",
    order: 40,
    file: "runs-guide.md",
  },
  {
    slug: ["packs"],
    title: "Scenario Packs",
    description: "Batch testing, regression suites, and aggregate outcomes.",
    section: "Operations",
    order: 50,
    file: "packs-guide.md",
  },
  {
    slug: ["schedules"],
    title: "Automated Schedules",
    description: "Recurring pack runs, cron definitions, and monitoring.",
    section: "Operations",
    order: 60,
    file: "schedules-guide.md",
  },
  {
    slug: ["examples"],
    title: "Example Catalog",
    description: "Curated graph, AI, pack, and direct HTTP transport examples.",
    section: "Operations",
    order: 65,
    file: "examples-catalog.md",
  },
  {
    slug: ["administration"],
    title: "Administration",
    description: "User management, tenant registry, and system configuration.",
    section: "Administration",
    order: 70,
    file: "admin-guide.md",
  },
  {
    slug: ["admin-users"],
    title: "User Admin",
    description: "Tenant-scoped user management, session revocation, and recovery actions.",
    section: "Administration",
    order: 72,
    file: "admin-users-guide.md",
  },
  {
    slug: ["admin-tenants"],
    title: "Tenant Admin",
    description: "Platform-level tenant lifecycle, overrides, quotas, and suspension.",
    section: "Administration",
    order: 74,
    file: "admin-tenants-guide.md",
  },
  {
    slug: ["admin-system"],
    title: "System Admin",
    description: "Platform health, feature defaults, and quota default management.",
    section: "Administration",
    order: 76,
    file: "admin-system-guide.md",
  },
  {
    slug: ["admin-sip"],
    title: "SIP Admin",
    description: "SIP trunk inventory, registry sync, and telephony visibility.",
    section: "Administration",
    order: 78,
    file: "admin-sip-guide.md",
  },
  {
    slug: ["audit-logs"],
    title: "Audit Logs",
    description: "System-wide tracking of administrative and operational actions.",
    section: "Administration",
    order: 80,
    file: "audit-guide.md",
  },
];

const DOCS_ROOT = path.join(process.cwd(), "content", "docs");

export function getDocsSections(): DocsSection[] {
  const sections = new Map<string, DocsPageMeta[]>();
  for (const page of DOCS_PAGES) {
    const bucket = sections.get(page.section) ?? [];
    bucket.push(page);
    sections.set(page.section, bucket);
  }

  return Array.from(sections.entries())
    .map(([title, pages]) => ({
      title,
      pages: [...pages].sort((left, right) => left.order - right.order),
    }))
    .sort((left, right) => left.pages[0].order - right.pages[0].order);
}

export function getDefaultDocsPage(): DocsPageMeta {
  return [...DOCS_PAGES].sort((left, right) => left.order - right.order)[0];
}

export function getDocsPageBySlug(slugParts?: string[] | null): DocsPageMeta | null {
  if (!slugParts || slugParts.length === 0) {
    return getDefaultDocsPage();
  }
  const normalized = slugParts.map((part) => part.trim()).filter(Boolean);
  return (
    DOCS_PAGES.find(
      (page) =>
        page.slug.length === normalized.length &&
        page.slug.every((part, index) => part === normalized[index])
    ) ?? null
  );
}

export async function readDocsPageContent(page: DocsPageMeta): Promise<string> {
  const filePath = path.join(DOCS_ROOT, page.file);
  return fs.readFile(filePath, "utf8");
}

export function docsHref(page: DocsPageMeta): string {
  return `/docs/${page.slug.join("/")}`;
}

export function getAllDocsPages(): DocsPageMeta[] {
  return [...DOCS_PAGES].sort((left, right) => left.order - right.order);
}
