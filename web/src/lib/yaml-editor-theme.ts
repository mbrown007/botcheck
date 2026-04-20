import { tags } from "@lezer/highlight";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorView } from "@codemirror/view";

const yamlEditorViewTheme = EditorView.theme(
  {
    "&": {
      color: "rgb(var(--editor-text))",
      backgroundColor: "rgb(var(--editor-bg))",
    },
    ".cm-content": {
      caretColor: "rgb(var(--editor-text))",
      fontSize: "13px",
      lineHeight: "1.55",
    },
    ".cm-gutters": {
      backgroundColor: "rgb(var(--editor-bg))",
      color: "rgb(var(--editor-muted))",
      border: "none",
    },
    ".cm-activeLineGutter": {
      color: "rgb(var(--text-secondary))",
    },
    ".cm-activeLine": {
      backgroundColor: "rgb(var(--editor-surface))",
    },
    ".cm-selectionBackground, &.cm-focused .cm-selectionBackground, ::selection": {
      backgroundColor: "rgb(var(--editor-accent) / 0.32)",
    },
    ".cm-cursor, .cm-dropCursor": {
      borderLeftColor: "rgb(var(--editor-text))",
    },
  },
  { dark: false }
);

const yamlEditorHighlightStyle = HighlightStyle.define([
  { tag: tags.propertyName, color: "rgb(var(--editor-accent))", fontWeight: "600" },
  { tag: tags.keyword, color: "rgb(var(--editor-accent))" },
  { tag: [tags.string, tags.special(tags.string)], color: "rgb(var(--editor-string))" },
  { tag: tags.atom, color: "rgb(var(--editor-text))" },
  { tag: [tags.number, tags.integer, tags.float], color: "rgb(var(--editor-number))" },
  { tag: [tags.bool, tags.null], color: "rgb(var(--editor-boolean))" },
  { tag: tags.comment, color: "rgb(var(--editor-comment))", fontStyle: "italic" },
  { tag: tags.operator, color: "rgb(var(--editor-punctuation))" },
  { tag: tags.punctuation, color: "rgb(var(--editor-punctuation))" },
]);

export const yamlEditorExtensions = [
  yamlEditorViewTheme,
  syntaxHighlighting(yamlEditorHighlightStyle),
];
