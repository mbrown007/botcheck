"use client";

import { Boxes, Mic, SearchCheck, Waves } from "lucide-react";

import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { TableState } from "@/components/ui/table-state";
import type { ProviderAvailabilitySummaryResponse } from "@/lib/api";
import {
  formatAvailableProviderLabel,
  formatProviderCredentialSource,
  groupAvailableProvidersByCapability,
  type ProviderCapabilityKind,
} from "@/lib/provider-availability";

const CAPABILITY_META: Record<
  ProviderCapabilityKind,
  { label: string; icon: typeof Mic; emptyMessage: string }
> = {
  tts: {
    label: "Speech synthesis",
    icon: Waves,
    emptyMessage: "No tenant-ready TTS providers.",
  },
  stt: {
    label: "Speech recognition",
    icon: Mic,
    emptyMessage: "No tenant-ready STT providers.",
  },
  llm: {
    label: "LLM",
    icon: Boxes,
    emptyMessage: "No tenant-ready LLM providers.",
  },
  judge: {
    label: "Eval judges",
    icon: SearchCheck,
    emptyMessage: "No tenant-ready judge providers.",
  },
};

export function TenantProviderAccessCard({
  title,
  description,
  providers,
  capabilities,
  loading = false,
  errorMessage = null,
  emptyMessage = "No tenant-assigned providers are currently available.",
  testId,
}: {
  title: string;
  description: string;
  providers: ProviderAvailabilitySummaryResponse[] | undefined;
  capabilities: ProviderCapabilityKind[];
  loading?: boolean;
  errorMessage?: string | null;
  emptyMessage?: string;
  testId?: string;
}) {
  const groups = groupAvailableProvidersByCapability(providers, capabilities);
  const hasAnyProviders = groups.some((group) => group.items.length > 0);

  return (
    <Card data-testid={testId}>
      <CardHeader>
        <div>
          <p className="text-sm font-medium text-text-secondary">{title}</p>
          <p className="mt-1 text-xs text-text-muted">{description}</p>
        </div>
      </CardHeader>
      <CardBody className="space-y-4">
        {loading ? <TableState kind="loading" message="Loading tenant provider access…" columns={1} rows={3} /> : null}
        {errorMessage ? <TableState kind="error" message={errorMessage} columns={1} /> : null}
        {!loading && !errorMessage && !hasAnyProviders ? (
          <TableState kind="empty" title="No providers available" message={emptyMessage} columns={1} />
        ) : null}
        {!loading && !errorMessage && hasAnyProviders
          ? groups.map((group) => {
              const meta = CAPABILITY_META[group.capability];
              const Icon = meta.icon;
              return (
                <div
                  key={group.capability}
                  className="rounded-xl border border-border bg-bg-elevated/40 px-4 py-4"
                >
                  <div className="flex items-center gap-2">
                    <Icon className="h-4 w-4 text-text-muted" />
                    <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
                      {meta.label}
                    </p>
                  </div>
                  {group.items.length === 0 ? (
                    <p className="mt-3 text-xs text-text-secondary">{meta.emptyMessage}</p>
                  ) : (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {group.items.map((item) => (
                        <div
                          key={item.provider_id}
                          className="rounded-lg border border-border bg-bg-surface px-3 py-2"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium text-text-primary">
                              {formatAvailableProviderLabel(item)}
                            </span>
                            <StatusBadge
                              value={item.credential_source === "db_encrypted" ? "pass" : "pending"}
                              label={formatProviderCredentialSource(item.credential_source)}
                            />
                          </div>
                          <p className="mt-1 text-[11px] text-text-muted">
                            {item.runtime_scopes.join(" · ")}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })
          : null}
      </CardBody>
    </Card>
  );
}
