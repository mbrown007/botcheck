import type { ScenarioSummary } from "@/lib/api/types";

interface BuilderScenarioAccessState {
  shouldDeferLoad: boolean;
  shouldRedirectToAIScenarios: boolean;
  targetScenario: ScenarioSummary | null;
}

export function filterGraphScenarios(
  scenarios: readonly ScenarioSummary[] | null | undefined
): ScenarioSummary[] {
  return (scenarios ?? []).filter((scenario) => scenario.scenario_kind !== "ai");
}

export function resolveBuilderScenarioAccess(params: {
  scenarioId: string | null;
  scenarios: readonly ScenarioSummary[] | null | undefined;
  scenariosResolved: boolean;
}): BuilderScenarioAccessState {
  const { scenarioId, scenarios, scenariosResolved } = params;

  if (!scenarioId) {
    return {
      shouldDeferLoad: false,
      shouldRedirectToAIScenarios: false,
      targetScenario: null,
    };
  }

  if (!scenariosResolved) {
    return {
      shouldDeferLoad: true,
      shouldRedirectToAIScenarios: false,
      targetScenario: null,
    };
  }

  const targetScenario =
    (scenarios ?? []).find((scenario) => scenario.id === scenarioId) ?? null;

  if (targetScenario?.scenario_kind === "ai") {
    return {
      shouldDeferLoad: false,
      shouldRedirectToAIScenarios: true,
      targetScenario,
    };
  }

  return {
    shouldDeferLoad: false,
    shouldRedirectToAIScenarios: false,
    targetScenario,
  };
}
