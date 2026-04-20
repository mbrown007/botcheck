import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { TenantProviderQuotaCard } from "@/components/providers/tenant-provider-quota-card";
import type {
  ProviderAvailabilitySummaryResponse,
  TenantProviderQuotaListResponse,
  TenantProviderUsageListResponse,
} from "@/lib/api";

const quota: TenantProviderQuotaListResponse = {
  window_start: "2026-03-16T12:00:00Z",
  window_end: "2026-03-17T12:00:00Z",
  items: [
    {
      provider_id: "anthropic:claude-sonnet-4-6",
      vendor: "anthropic",
      model: "claude-sonnet-4-6",
      capability: "judge",
      metrics: [
        {
          metric: "input_tokens",
          limit_per_day: 100,
          used_24h: 82,
          remaining_24h: 18,
          soft_limit_pct: 70,
          percent_used: 82,
          status: "watch",
          soft_limit_reached: true,
          hard_limit_reached: false,
        },
      ],
    },
  ],
};

const usage: TenantProviderUsageListResponse = {
  window_start: "2026-03-16T12:00:00Z",
  window_end: "2026-03-17T12:00:00Z",
  items: [
    {
      provider_id: "anthropic:claude-sonnet-4-6",
      vendor: "anthropic",
      model: "claude-sonnet-4-6",
      capability: "judge",
      runtime_scopes: ["judge"],
      last_recorded_at: "2026-03-17T11:50:00Z",
      input_tokens_24h: 82,
      output_tokens_24h: 20,
      audio_seconds_24h: 0,
      characters_24h: 0,
      sip_minutes_24h: 0,
      request_count_24h: 1,
      calculated_cost_microcents_24h: 900,
    },
    {
      provider_id: "openai:gpt-4o-mini-tts",
      vendor: "openai",
      model: "gpt-4o-mini-tts",
      capability: "tts",
      runtime_scopes: ["agent", "api"],
      last_recorded_at: "2026-03-17T11:40:00Z",
      input_tokens_24h: 0,
      output_tokens_24h: 0,
      audio_seconds_24h: 0,
      characters_24h: 240,
      sip_minutes_24h: 0,
      request_count_24h: 2,
      calculated_cost_microcents_24h: 120,
    },
  ],
};

const providers: ProviderAvailabilitySummaryResponse[] = [
  {
    provider_id: "anthropic:claude-sonnet-4-6",
    vendor: "anthropic",
    model: "claude-sonnet-4-6",
    capability: "judge",
    runtime_scopes: ["judge"],
    credential_source: "db_encrypted",
    configured: true,
    availability_status: "available",
    supports_tenant_credentials: false,
  },
  {
    provider_id: "openai:gpt-4o-mini-tts",
    vendor: "openai",
    model: "gpt-4o-mini-tts",
    capability: "tts",
    runtime_scopes: ["agent", "api"],
    credential_source: "env",
    configured: true,
    availability_status: "available",
    supports_tenant_credentials: false,
  },
];

test("TenantProviderQuotaCard renders quota-backed and usage-only provider sections", () => {
  const markup = renderToStaticMarkup(
    <TenantProviderQuotaCard
      quota={quota}
      usage={usage}
      availableProviders={providers}
    />
  );

  assert.match(markup, /Provider usage &amp; quotas/);
  assert.match(markup, /1 policy/);
  assert.match(markup, /2 provider lanes/);
  assert.match(markup, /1 usage-only provider/);
  assert.match(markup, /provider quota needs attention/i);
  assert.match(markup, /anthropic:claude-sonnet-4-6/);
  assert.match(markup, /openai:gpt-4o-mini-tts/);
  assert.match(markup, /quota not configured/);
});

test("TenantProviderQuotaCard renders loading skeleton when loading=true", () => {
  const markup = renderToStaticMarkup(
    <TenantProviderQuotaCard loading={true} />
  );

  assert.match(markup, /Loading provider usage and quotas/);
  // Should not render summary stats while loading
  assert.doesNotMatch(markup, /Quota-backed/);
});

test("TenantProviderQuotaCard renders error message when errorMessage is set", () => {
  const markup = renderToStaticMarkup(
    <TenantProviderQuotaCard loading={false} errorMessage="Failed to load quota data" />
  );

  assert.match(markup, /Failed to load quota data/);
  // Should not render summary stats on error
  assert.doesNotMatch(markup, /Quota-backed/);
});

test("TenantProviderQuotaCard shows error over loading skeleton when both are active (re-fetch after error)", () => {
  const markup = renderToStaticMarkup(
    <TenantProviderQuotaCard loading={true} errorMessage="Network error" />
  );

  assert.match(markup, /Network error/);
  assert.doesNotMatch(markup, /Loading provider usage/);
});

test("TenantProviderQuotaCard warning panel shows fail tone when hard limit exceeded", () => {
  const hardLimitQuota: TenantProviderQuotaListResponse = {
    window_start: "2026-03-16T12:00:00Z",
    window_end: "2026-03-17T12:00:00Z",
    items: [
      {
        provider_id: "anthropic:claude-sonnet-4-6",
        vendor: "anthropic",
        model: "claude-sonnet-4-6",
        capability: "judge",
        metrics: [
          {
            metric: "input_tokens",
            limit_per_day: 100,
            used_24h: 100,
            remaining_24h: 0,
            soft_limit_pct: 70,
            percent_used: 100,
            status: "exceeded",
            soft_limit_reached: true,
            hard_limit_reached: true,
          },
        ],
      },
    ],
  };

  const markup = renderToStaticMarkup(
    <TenantProviderQuotaCard quota={hardLimitQuota} usage={{ window_start: "", window_end: "", items: [] }} />
  );

  assert.match(markup, /over limit/i);
  assert.match(markup, /over limit/); // item badgeLabel
});

test("TenantProviderQuotaCard warning panel shows info tone when provider has no quota policy", () => {
  const usageOnly: TenantProviderUsageListResponse = {
    window_start: "2026-03-16T12:00:00Z",
    window_end: "2026-03-17T12:00:00Z",
    items: [
      {
        provider_id: "openai:gpt-4o-mini-tts",
        vendor: "openai",
        model: "gpt-4o-mini-tts",
        capability: "tts",
        runtime_scopes: ["agent"],
        last_recorded_at: "2026-03-17T11:40:00Z",
        input_tokens_24h: 0,
        output_tokens_24h: 0,
        audio_seconds_24h: 0,
        characters_24h: 240,
        sip_minutes_24h: 0,
        request_count_24h: 2,
        calculated_cost_microcents_24h: 120,
      },
    ],
  };

  const markup = renderToStaticMarkup(
    <TenantProviderQuotaCard quota={{ window_start: "", window_end: "", items: [] }} usage={usageOnly} />
  );

  assert.match(markup, /no quota policy/i);
  assert.match(markup, /no policy/); // item badgeLabel
});
