"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
} from "react";

import {
  BUILDER_PANEL_WIDTH_DEFAULT,
  clampBuilderPanelWidth,
  readBuilderPanelPrefs,
  writeBuilderPanelPrefs,
} from "@/lib/builder-panel-storage";
import type { BuilderFocusField } from "@/lib/builder-draft-seed";

export type BuilderMobilePane = "visual" | "yaml";

type UseBuilderWorkspaceLayoutArgs = {
  focusField: BuilderFocusField | null;
  hasStructuralErrors: boolean;
  parseError: string | null;
};

export function useBuilderWorkspaceLayout({
  focusField,
  hasStructuralErrors,
  parseError,
}: UseBuilderWorkspaceLayoutArgs) {
  const initialPanelPrefs = useMemo(() => readBuilderPanelPrefs(), []);
  const [panelOpen, setPanelOpen] = useState(initialPanelPrefs?.panelOpen ?? true);
  const [turnBlocksOpen, setTurnBlocksOpen] = useState(
    initialPanelPrefs?.turnBlocksOpen ?? true,
  );
  const [libraryOpen, setLibraryOpen] = useState(initialPanelPrefs?.libraryOpen ?? true);
  const [metadataOpen, setMetadataOpen] = useState(initialPanelPrefs?.metadataOpen ?? true);
  const [yamlOpen, setYamlOpen] = useState(initialPanelPrefs?.yamlOpen ?? true);
  const [panelWidth, setPanelWidth] = useState(
    initialPanelPrefs?.panelWidth ?? BUILDER_PANEL_WIDTH_DEFAULT,
  );
  const [isResizingPanel, setIsResizingPanel] = useState(false);
  const [mobilePane, setMobilePane] = useState<BuilderMobilePane>("visual");
  const layoutGridRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    writeBuilderPanelPrefs({
      panelOpen,
      turnBlocksOpen,
      libraryOpen,
      metadataOpen,
      yamlOpen,
      panelWidth,
    });
  }, [libraryOpen, metadataOpen, panelOpen, panelWidth, turnBlocksOpen, yamlOpen]);

  useEffect(() => {
    if (!(parseError || hasStructuralErrors)) {
      return;
    }
    setPanelOpen(true);
    setYamlOpen(true);
  }, [hasStructuralErrors, parseError]);

  useEffect(() => {
    if (focusField !== "metadata-id") {
      return;
    }
    setPanelOpen(true);
    setMetadataOpen(true);
  }, [focusField]);

  useEffect(() => {
    if (!isResizingPanel || !panelOpen) {
      return;
    }
    function onMouseMove(event: MouseEvent) {
      const container = layoutGridRef.current;
      if (!container) {
        return;
      }
      const rect = container.getBoundingClientRect();
      const nextWidth = clampBuilderPanelWidth(Math.round(rect.right - event.clientX));
      setPanelWidth(nextWidth);
    }
    function onMouseUp() {
      setIsResizingPanel(false);
    }
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [isResizingPanel, panelOpen]);

  const handleStartPanelResize = useCallback(
    (event: ReactMouseEvent<HTMLButtonElement>) => {
      if (!panelOpen) {
        return;
      }
      event.preventDefault();
      setIsResizingPanel(true);
    },
    [panelOpen],
  );

  const panelGridStyle = useMemo(
    () =>
      ({
        "--builder-panel-width": panelOpen ? `${panelWidth}px` : "28px",
      }) as CSSProperties,
    [panelOpen, panelWidth],
  );

  const collapsePanel = useCallback(() => setPanelOpen(false), []);
  const expandPanel = useCallback(() => setPanelOpen(true), []);
  const toggleTurnBlocksOpen = useCallback(() => setTurnBlocksOpen((prev) => !prev), []);
  const toggleLibraryOpen = useCallback(() => setLibraryOpen((prev) => !prev), []);
  const toggleMetadataOpen = useCallback(() => setMetadataOpen((prev) => !prev), []);
  const toggleYamlOpen = useCallback(() => setYamlOpen((prev) => !prev), []);

  return {
    collapsePanel,
    expandPanel,
    handleStartPanelResize,
    isResizingPanel,
    layoutGridRef,
    libraryOpen,
    metadataOpen,
    mobilePane,
    panelGridStyle,
    panelOpen,
    setMobilePane,
    toggleLibraryOpen,
    toggleMetadataOpen,
    toggleTurnBlocksOpen,
    toggleYamlOpen,
    turnBlocksOpen,
    yamlOpen,
  };
}
