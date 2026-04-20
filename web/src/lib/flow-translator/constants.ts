export { DECISION_OUTPUT_HANDLE_PREFIX } from "@/lib/decision-slots";

export const KNOWN_TOP_LEVEL_FIELDS = [
  "version",
  "id",
  "name",
  "namespace",
  "type",
  "description",
  "bot",
  "persona",
  "config",
  "scoring",
  "tags",
] as const;

export const DEFAULT_NODE_WIDTH = 260;
export const DEFAULT_NODE_HEIGHT = 88;
