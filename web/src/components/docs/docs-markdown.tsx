import React from "react";
import type { ReactNode } from "react";

function slugifyHeading(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-");
}

function renderInline(text: string): ReactNode[] {
  const parts = text
    .split(/(`[^`]+`|\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|\*[^*]+\*)/g)
    .filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={`inline-${index}`}
          className="rounded bg-bg-elevated px-1.5 py-0.5 font-mono text-[0.9em] text-text-primary"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      const [, label, href] = linkMatch;
      const external = href.startsWith("http://") || href.startsWith("https://");
      return (
        <a
          key={`inline-${index}`}
          href={href}
          target={external ? "_blank" : undefined}
          rel={external ? "noreferrer noopener" : undefined}
          className="text-brand underline decoration-brand/30 underline-offset-4 hover:text-brand-hover"
        >
          {label}
        </a>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={`inline-${index}`} className="font-semibold text-text-primary">
          {renderInline(part.slice(2, -2))}
        </strong>
      );
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return (
        <em key={`inline-${index}`} className="italic text-text-secondary">
          {renderInline(part.slice(1, -1))}
        </em>
      );
    }
    return <span key={`inline-${index}`}>{part}</span>;
  });
}

function renderParagraph(lines: string[], key: string) {
  if (lines.length === 0) return null;
  return (
    <p key={key} className="text-sm leading-7 text-text-secondary">
      {renderInline(lines.join(" "))}
    </p>
  );
}

export function DocsMarkdown({ source }: { source: string }) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let orderedItems: string[] = [];
  let codeFence: { language: string; lines: string[] } | null = null;
  let blockquote: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push(renderParagraph(paragraph, `p-${blocks.length}`));
      paragraph = [];
    }
  };

  const flushList = () => {
    if (listItems.length > 0) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="list-disc space-y-2 pl-5 text-sm text-text-secondary">
          {listItems.map((item, index) => (
            <li key={`li-${index}`}>{renderInline(item)}</li>
          ))}
        </ul>
      );
      listItems = [];
    }
    if (orderedItems.length > 0) {
      blocks.push(
        <ol key={`ol-${blocks.length}`} className="list-decimal space-y-2 pl-5 text-sm text-text-secondary">
          {orderedItems.map((item, index) => (
            <li key={`oli-${index}`}>{renderInline(item)}</li>
          ))}
        </ol>
      );
      orderedItems = [];
    }
  };

  const flushBlockquote = () => {
    if (blockquote.length > 0) {
      blocks.push(
        <blockquote
          key={`quote-${blocks.length}`}
          className="border-l-2 border-brand/30 pl-4 text-sm leading-7 text-text-secondary"
        >
          {renderInline(blockquote.join(" "))}
        </blockquote>
      );
      blockquote = [];
    }
  };

  const flushCodeFence = () => {
    if (codeFence) {
      blocks.push(
        <div key={`code-${blocks.length}`} className="overflow-hidden rounded-xl border border-border bg-[#0f172a]">
          {codeFence.language ? (
            <div className="border-b border-white/10 px-4 py-2 text-[11px] uppercase tracking-[0.18em] text-slate-400">
              {codeFence.language}
            </div>
          ) : null}
          <pre className="overflow-x-auto p-4 text-sm text-slate-100">
            <code>{codeFence.lines.join("\n")}</code>
          </pre>
        </div>
      );
      codeFence = null;
    }
  };

  for (const line of lines) {
    if (codeFence) {
      if (line.startsWith("```")) {
        flushCodeFence();
      } else {
        codeFence.lines.push(line);
      }
      continue;
    }

    if (line.startsWith("```")) {
      flushParagraph();
      flushList();
      flushBlockquote();
      codeFence = { language: line.slice(3).trim(), lines: [] };
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      flushBlockquote();
      continue;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      flushBlockquote();
      const [, hashes, headingText] = headingMatch;
      const headingId = slugifyHeading(headingText);
      const level = hashes.length;
      const className =
        level === 1
          ? "text-3xl font-semibold tracking-tight text-text-primary"
          : level === 2
            ? "text-xl font-semibold text-text-primary"
            : "text-base font-semibold uppercase tracking-[0.14em] text-text-primary";
      const Tag = level === 1 ? "h1" : level === 2 ? "h2" : "h3";
      blocks.push(
        <Tag key={`h-${blocks.length}`} id={headingId} className={className}>
          {headingText}
        </Tag>
      );
      continue;
    }

    if (/^\s*---+\s*$/.test(line)) {
      flushParagraph();
      flushList();
      flushBlockquote();
      blocks.push(<hr key={`hr-${blocks.length}`} className="border-border" />);
      continue;
    }

    const unorderedMatch = line.match(/^\s*[-*]\s+(.*)$/);
    if (unorderedMatch) {
      flushParagraph();
      flushBlockquote();
      listItems.push(unorderedMatch[1]);
      continue;
    }

    const orderedMatch = line.match(/^\s*\d+\.\s+(.*)$/);
    if (orderedMatch) {
      flushParagraph();
      flushBlockquote();
      orderedItems.push(orderedMatch[1]);
      continue;
    }

    const quoteMatch = line.match(/^\s*>\s?(.*)$/);
    if (quoteMatch) {
      flushParagraph();
      flushList();
      blockquote.push(quoteMatch[1]);
      continue;
    }

    paragraph.push(line.trim());
  }

  flushParagraph();
  flushList();
  flushBlockquote();
  flushCodeFence();

  return <div className="space-y-6">{blocks}</div>;
}
