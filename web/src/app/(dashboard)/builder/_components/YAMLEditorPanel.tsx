"use client";

import CodeMirror from "@uiw/react-codemirror";
import { yaml as yamlLanguage } from "@codemirror/lang-yaml";
import { yamlEditorExtensions } from "@/lib/yaml-editor-theme";
import { useBuilderStore } from "@/lib/builder-store";

interface YAMLEditorPanelProps {
  open: boolean;
  onToggle: () => void;
  loading: boolean;
  saveState: "idle" | "saving";
  onApplyYaml: () => void;
}

export function YAMLEditorPanel({ open, onToggle, loading, saveState, onApplyYaml }: YAMLEditorPanelProps) {
  const yamlDraft = useBuilderStore((state) => state.yamlDraft);
  const yamlCanonical = useBuilderStore((state) => state.yamlCanonical);
  const setYamlDraft = useBuilderStore((state) => state.setYamlDraft);

  return (
    <div className="rounded-md border border-border bg-bg-elevated">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <h2 className="text-sm font-semibold text-text-primary">YAML Editor</h2>
        <div className="flex items-center gap-2">
          <span className="rounded border border-border bg-bg-base px-2 py-0.5 text-[11px] font-mono text-text-muted">
            {yamlDraft.length} chars
          </span>
          <span className="text-xs text-text-muted">{open ? "▾" : "▸"}</span>
        </div>
      </button>
      {open && (
        <div className="border-t border-border px-3 pb-3">
          <p className="mb-2 mt-2 text-xs text-text-muted">
            Draft edits apply on blur or via Apply YAML.
          </p>
          <CodeMirror
            value={loading ? "Loading..." : yamlDraft}
            height="480px"
            extensions={[yamlLanguage(), ...yamlEditorExtensions]}
            editable={!loading && saveState !== "saving"}
            onChange={(value) => setYamlDraft(value)}
            onBlur={() => {
              if (yamlDraft !== yamlCanonical) {
                onApplyYaml();
              }
            }}
            className="rounded-md border border-border bg-bg-base text-sm"
          />
        </div>
      )}
    </div>
  );
}
