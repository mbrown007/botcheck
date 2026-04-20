import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DocsMarkdown } from "@/components/docs/docs-markdown";

test("DocsMarkdown renders emphasis, links, anchors, and horizontal rules", () => {
  const markup = renderToStaticMarkup(
    <DocsMarkdown
      source={[
        "# Platform Guide",
        "",
        "See the [Core Concepts](#core-concepts) section.",
        "",
        "## Core Concepts",
        "",
        "BotCheck supports **bold emphasis**, *italic notes*, and `inline code`.",
        "",
        "---",
      ].join("\n")}
    />
  );

  assert.match(markup, /<h1 id="platform-guide"/);
  assert.match(markup, /<h2 id="core-concepts"/);
  assert.match(markup, /href="#core-concepts"/);
  assert.match(markup, /<strong[^>]*>.*bold emphasis.*<\/strong>/);
  assert.match(markup, /<em[^>]*>.*italic notes.*<\/em>/);
  assert.match(markup, /<code[^>]*>inline code<\/code>/);
  assert.match(markup, /<hr/);
});
