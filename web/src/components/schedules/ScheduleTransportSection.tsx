import type { BotDestinationSummary } from "@/lib/api";
import { transportProfileOptionLabel } from "@/lib/destination-display";

export function ScheduleTransportSection({
  mode,
  botEndpoint,
  setBotEndpoint,
  destinationsEnabled,
  destinations,
  destinationId,
  setDestinationId,
  dispatchHint,
}: {
  mode: "create" | "edit";
  botEndpoint: string;
  setBotEndpoint: (value: string) => void;
  destinationsEnabled: boolean;
  destinations?: BotDestinationSummary[];
  destinationId: string;
  setDestinationId: (value: string) => void;
  dispatchHint: string;
}) {
  const testIdPrefix = mode === "create" ? "create" : "edit";

  return (
    <>
      <label className="block">
        <span className="mb-1.5 block text-xs text-text-secondary">Target Override (optional)</span>
        <input
          data-testid={`${testIdPrefix}-schedule-bot-endpoint`}
          type="text"
          value={botEndpoint}
          onChange={(e) => setBotEndpoint(e.target.value)}
          placeholder="Use profile default or enter an endpoint / SIP target"
          className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-border-focus focus:outline-none"
        />
        <p className="mt-1 text-[11px] text-text-muted">
          Overrides the selected transport profile target. For SIP this is the dialed number or URI; for HTTP this is the request endpoint.
        </p>
      </label>
      {destinationsEnabled ? (
        <label className="block">
          <span className="mb-1.5 block text-xs text-text-secondary">Transport Profile (optional)</span>
          <select
            data-testid={`${testIdPrefix}-schedule-destination-id`}
            value={destinationId}
            onChange={(e) => setDestinationId(e.target.value)}
            className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
          >
            <option value="">Use schedule target defaults</option>
            {destinations?.map((destination) => (
              <option
                key={destination.destination_id}
                value={destination.destination_id}
                disabled={!destination.is_active}
              >
                {transportProfileOptionLabel(destination)}
              </option>
            ))}
          </select>
          <p className="mt-1 text-[11px] text-text-muted">
            Applies stored protocol-specific settings such as endpoint, auth headers, caller ID, and capacity controls when available.
          </p>
        </label>
      ) : null}
      <p className="md:col-span-2 text-[11px] text-text-muted">{dispatchHint}</p>
    </>
  );
}
