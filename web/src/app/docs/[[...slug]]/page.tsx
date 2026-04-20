import Link from "next/link";
import type { Route } from "next";
import { notFound } from "next/navigation";
import { BookOpen, ChevronRight } from "lucide-react";
import { DocsMarkdown } from "@/components/docs/docs-markdown";
import {
  docsHref,
  getAllDocsPages,
  getDefaultDocsPage,
  getDocsPageBySlug,
  getDocsSections,
  readDocsPageContent,
} from "@/lib/docs";
import { cn } from "@/lib/utils";

export async function generateStaticParams() {
  return getAllDocsPages().map((page) => ({ slug: page.slug }));
}

export default async function DocsPage({
  params,
}: {
  params: Promise<{ slug?: string[] }>;
}) {
  const { slug } = await params;
  const page = getDocsPageBySlug(slug);
  if (!page) {
    notFound();
  }
  const content = await readDocsPageContent(page);
  const sections = getDocsSections();
  const defaultPage = getDefaultDocsPage();

  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      <header className="sticky top-0 z-30 border-b border-border bg-bg-base/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <Link href={"/" as Route} className="flex items-center gap-2">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-brand-muted text-brand">
              <BookOpen className="h-4 w-4" />
            </span>
            <div>
              <div className="text-sm font-semibold">BotCheck Docs</div>
              <div className="text-xs text-text-muted">Built into the app deployment</div>
            </div>
          </Link>
          <div className="flex items-center gap-3">
            <Link
              href={"/scenarios" as Route}
              className="rounded-md border border-border bg-bg-surface px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:border-brand hover:text-text-primary"
            >
              Back to App
            </Link>
            <Link
              href={(docsHref(defaultPage) || "/docs") as Route}
              className="text-sm text-text-secondary transition-colors hover:text-text-primary"
            >
              Documentation
            </Link>
            <Link
              href={"/login" as Route}
              className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-text-inverse transition-colors hover:bg-brand-hover"
            >
              Login
            </Link>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-8 px-6 py-8 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="rounded-2xl border border-border bg-bg-surface p-4">
            <div className="mb-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                Documentation
              </p>
              <p className="mt-2 text-sm text-text-secondary">
                Markdown-backed product docs shipped with the same app deployment.
              </p>
            </div>
            <nav className="space-y-4">
              {sections.map((section) => (
                <div key={section.title}>
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                    {section.title}
                  </p>
                  <div className="space-y-1">
                    {section.pages.map((entry) => {
                      const active = entry.slug.join("/") === page.slug.join("/");
                      return (
                        <Link
                          key={entry.slug.join("/")}
                          href={docsHref(entry) as Route}
                          className={cn(
                            "block rounded-xl border px-3 py-2 transition-colors",
                            active
                              ? "border-brand/20 bg-brand-muted text-brand"
                              : "border-transparent text-text-secondary hover:border-border hover:bg-bg-elevated hover:text-text-primary"
                          )}
                        >
                          <div className="text-sm font-medium">{entry.title}</div>
                          <div className="mt-1 text-xs text-text-muted">{entry.description}</div>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))}
            </nav>
          </div>
        </aside>

        <main className="min-w-0">
          <div className="rounded-3xl border border-border bg-bg-surface shadow-sm">
            <div className="border-b border-border px-6 py-5">
              <div className="flex items-center gap-2 text-xs text-text-muted">
                <Link href={(docsHref(defaultPage) || "/docs") as Route} className="hover:text-text-primary">
                  Docs
                </Link>
                <ChevronRight className="h-3.5 w-3.5" />
                <span>{page.section}</span>
              </div>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-text-primary">
                {page.title}
              </h1>
              <p className="mt-2 max-w-3xl text-sm leading-7 text-text-secondary">
                {page.description}
              </p>
            </div>
            <div className="px-6 py-8">
              <DocsMarkdown source={content} />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
