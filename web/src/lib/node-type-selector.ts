// getBuilderTurnKind reads only the canonical kind field, so passing any
// BuilderTurn-shaped value here is always safe once builder YAML is normalized.
import { getBuilderTurnKind, type BuilderTurn } from "@/lib/builder-types";

export type BuilderNodeType =
  | "harnessNode"
  | "botNode"
  | "hangupNode"
  | "waitNode"
  | "timeRouteNode";

export function selectNodeTypeForTurn(turn: BuilderTurn): BuilderNodeType {
  switch (getBuilderTurnKind(turn)) {
    case "hangup":
      return "hangupNode";
    case "wait":
      return "waitNode";
    case "time_route":
      return "timeRouteNode";
    case "bot_listen":
      return "botNode";
    default:
      return "harnessNode";
  }
}
