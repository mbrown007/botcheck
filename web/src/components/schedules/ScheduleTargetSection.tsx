import type { ScheduleTargetType } from "@/components/schedules/schedule-form-helpers";

export function ScheduleTargetSection({
  targetType,
  setTargetType,
  scenarioId,
  setScenarioId,
  aiEnabled,
  aiScenarioId,
  setAiScenarioId,
  packId,
  setPackId,
  graphScenarios,
  aiScenarios,
  packs,
  mode,
}: {
  targetType: ScheduleTargetType;
  setTargetType: (value: ScheduleTargetType) => void;
  scenarioId: string;
  setScenarioId: (value: string) => void;
  aiEnabled: boolean;
  aiScenarioId: string;
  setAiScenarioId: (value: string) => void;
  packId: string;
  setPackId: (value: string) => void;
  graphScenarios: Array<{ id: string; name: string }>;
  aiScenarios?: Array<{ ai_scenario_id: string; name: string }>;
  packs?: Array<{ pack_id: string; name: string }>;
  mode: "create" | "edit";
}) {
  const testIdPrefix = mode === "create" ? "create" : "edit";

  return (
    <>
      <label className="block">
        <span className="mb-1.5 block text-xs text-text-secondary">Target Type</span>
        <select
          data-testid={`${testIdPrefix}-schedule-target-type`}
          value={targetType}
          onChange={(e) => setTargetType(e.target.value as ScheduleTargetType)}
          className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
        >
          <option value="scenario">Single Scenario</option>
          <option value="pack">Scenario Pack</option>
        </select>
      </label>

      <label className="block">
        <span className="mb-1.5 block text-xs text-text-secondary">
          {targetType === "scenario" ? "Graph Scenario" : "Pack"}
        </span>
        <select
          data-testid={`${testIdPrefix}-schedule-target-id`}
          value={targetType === "scenario" ? scenarioId : packId}
          onChange={(e) => {
            if (targetType === "scenario") {
              setScenarioId(e.target.value);
              if (e.target.value) {
                setAiScenarioId("");
              }
            } else {
              setPackId(e.target.value);
            }
          }}
          className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
        >
          {targetType === "scenario" ? (
            <>
              <option value="">Select graph scenario…</option>
              {graphScenarios.map((scenario) => (
                <option key={scenario.id} value={scenario.id}>
                  {scenario.name}
                </option>
              ))}
            </>
          ) : (
            <>
              <option value="">Select pack…</option>
              {packs?.map((pack) => (
                <option key={pack.pack_id} value={pack.pack_id}>
                  {pack.name}
                </option>
              ))}
            </>
          )}
        </select>
      </label>

      {targetType === "scenario" && aiEnabled ? (
        <label className="block">
          <span className="mb-1.5 block text-xs text-text-secondary">AI Scenario</span>
          <select
            data-testid={`${testIdPrefix}-schedule-ai-scenario-id`}
            value={aiScenarioId}
            onChange={(e) => {
              setAiScenarioId(e.target.value);
              if (e.target.value) {
                setScenarioId("");
              }
            }}
            className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
          >
            <option value="">Select AI scenario…</option>
            {aiScenarios?.map((scenario) => (
              <option key={scenario.ai_scenario_id} value={scenario.ai_scenario_id}>
                {scenario.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
    </>
  );
}
