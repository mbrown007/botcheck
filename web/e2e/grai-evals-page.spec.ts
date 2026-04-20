import { expect, test, type Page, type Route } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute, type MockAppRole } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const SUITE_IMPORTED_ID = "gesuite_imported_1";
const SUITE_NATIVE_ID = "gesuite_native_1";
const SUITE_CREATED_ID = "gesuite_created_1";
const SUITE_IMPORTED_FROM_DIALOG_ID = "gesuite_imported_dialog_1";
const RUN_ID = "gerun_eval_1";
const RUN_HISTORY_ID = "gerun_eval_prev_1";
const RESULT_ONE_ID = "geresult_1";
const RESULT_TWO_ID = "geresult_2";
const RESULT_HISTORY_ID = "geresult_history_1";
const HTTP_DESTINATION_ID = "dest_http_eval_1";
const HTTP_DESTINATION_B_ID = "dest_http_eval_2";

async function ok(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function suiteSummary(
  suiteId: string,
  name: string,
  options: { description?: string | null; promptCount?: number; caseCount?: number; imported?: boolean } = {}
) {
  return {
    suite_id: suiteId,
    name,
    description: options.description ?? null,
    prompt_count: options.promptCount ?? 2,
    case_count: options.caseCount ?? 2,
    has_source_yaml: options.imported ?? false,
    created_at: "2026-03-15T08:00:00Z",
    updated_at: "2026-03-15T08:30:00Z",
  };
}

function suiteDetail(
  suiteId: string,
  name: string,
  options: { description?: string | null; sourceYaml?: string | null } = {}
) {
  return {
    suite_id: suiteId,
    name,
    description: options.description ?? null,
    source_yaml: options.sourceYaml ?? null,
    metadata_json: {},
    prompts: [
      {
        prompt_id: `${suiteId}_prompt_helpful`,
        label: "helpful",
        prompt_text: "Answer clearly: {{question}}",
        metadata_json: {},
      },
      {
        prompt_id: `${suiteId}_prompt_brief`,
        label: "brief",
        prompt_text: "Reply in one sentence: {{question}}",
        metadata_json: {},
      },
    ],
    cases: [
      {
        case_id: `${suiteId}_case_refund`,
        description: "Refund policy",
        vars_json: { question: "What is the refund policy?" },
        assert_json: [
          {
            assertion_type: "contains",
            passed: null,
            score: null,
            threshold: null,
            weight: 1,
            raw_value: "refund",
            failure_reason: null,
            latency_ms: null,
          },
        ],
        tags_json: ["billing", "smoke-test"],
        metadata_json: {},
        import_threshold: null,
      },
      {
        case_id: `${suiteId}_case_cancel`,
        description: "Cancel subscription",
        vars_json: { question: "How do I cancel?" },
        assert_json: [
          {
            assertion_type: "llm-rubric",
            passed: null,
            score: null,
            threshold: 0.8,
            weight: 1,
            raw_value: "clarity",
            failure_reason: null,
            latency_ms: null,
          },
        ],
        tags_json: ["account", "retention"],
        metadata_json: {},
        import_threshold: 0.8,
      },
    ],
    created_at: "2026-03-15T08:00:00Z",
    updated_at: "2026-03-15T08:30:00Z",
  };
}

async function mockGraiApi(page: Page, role: MockAppRole): Promise<void> {
  const suites = [
    suiteSummary(SUITE_IMPORTED_ID, "Imported billing suite", {
      description: "Promptfoo imported smoke coverage",
      imported: true,
    }),
    suiteSummary(SUITE_NATIVE_ID, "Native account suite", {
      description: "Manually curated account flows",
    }),
  ];
  const suiteDetails = new Map<string, ReturnType<typeof suiteDetail>>([
    [
      SUITE_IMPORTED_ID,
      suiteDetail(SUITE_IMPORTED_ID, "Imported billing suite", {
        description: "Promptfoo imported smoke coverage",
        sourceYaml: "description: Billing suite\nprompts:\n  - raw: Answer clearly: {{question}}",
      }),
    ],
    [
      SUITE_NATIVE_ID,
      suiteDetail(SUITE_NATIVE_ID, "Native account suite", {
        description: "Manually curated account flows",
      }),
    ],
  ]);
  let runStatus = "running";
  const historyResult = {
    eval_result_id: RESULT_HISTORY_ID,
    destination_index: 0,
    transport_profile_id: HTTP_DESTINATION_ID,
    destination_label: "Billing HTTP Bot",
    prompt_id: `${SUITE_IMPORTED_ID}_prompt_helpful`,
    prompt_label: "helpful",
    case_id: `${SUITE_IMPORTED_ID}_case_refund`,
    case_description: "Refund policy",
    assertion_index: 0,
    assertion_type: "contains",
    passed: true,
    score: 1,
    threshold: null,
    weight: 1,
    raw_value: "refund",
    failure_reason: null,
    latency_ms: 430,
    tags_json: ["billing", "smoke-test"],
    raw_s3_key: "grai/raw/result-history.json",
    created_at: "2026-03-14T09:04:00Z",
  };
  const resultOne = {
    eval_result_id: RESULT_ONE_ID,
    destination_index: 0,
    transport_profile_id: HTTP_DESTINATION_ID,
    destination_label: "Billing HTTP Bot",
    prompt_id: `${SUITE_IMPORTED_ID}_prompt_helpful`,
    prompt_label: "helpful",
    case_id: `${SUITE_IMPORTED_ID}_case_refund`,
    case_description: "Refund policy",
    assertion_index: 0,
    assertion_type: "contains",
    passed: false,
    score: 0.4,
    threshold: null,
    weight: 1,
    raw_value: "refund",
    failure_reason: "Response missed refund guidance",
    latency_ms: 610,
    tags_json: ["billing", "smoke-test"],
    raw_s3_key: "grai/raw/result-one.json",
    created_at: "2026-03-15T09:03:00Z",
  };
  const resultTwo = {
    eval_result_id: RESULT_TWO_ID,
    destination_index: 1,
    transport_profile_id: HTTP_DESTINATION_B_ID,
    destination_label: "Billing HTTP Bot B",
    prompt_id: `${SUITE_IMPORTED_ID}_prompt_brief`,
    prompt_label: "brief",
    case_id: `${SUITE_IMPORTED_ID}_case_cancel`,
    case_description: "Cancel subscription",
    assertion_index: 0,
    assertion_type: "llm-rubric",
    passed: true,
    score: 0.91,
    threshold: 0.8,
    weight: 1,
    raw_value: "clarity",
    failure_reason: null,
    latency_ms: 780,
    tags_json: ["account", "retention"],
    raw_s3_key: "grai/raw/result-two.json",
    created_at: "2026-03-15T09:04:00Z",
  };
  const importedSuiteHistory = () => [
    {
      eval_run_id: RUN_ID,
      suite_id: SUITE_IMPORTED_ID,
      transport_profile_id: HTTP_DESTINATION_ID,
      transport_profile_ids: [HTTP_DESTINATION_ID, HTTP_DESTINATION_B_ID],
      destination_count: 2,
      destinations: [
        {
          destination_index: 0,
          transport_profile_id: HTTP_DESTINATION_ID,
          label: "Billing HTTP Bot",
        },
        {
          destination_index: 1,
          transport_profile_id: HTTP_DESTINATION_B_ID,
          label: "Billing HTTP Bot B",
        },
      ],
      status: runStatus,
      trigger_source: "manual",
      schedule_id: null,
      triggered_by: "user_e2e",
      prompt_count: 2,
      case_count: 2,
      total_pairs: 8,
      dispatched_count: 6,
      completed_count: 5,
      failed_count: 1,
      created_at: "2026-03-15T09:00:00Z",
      updated_at: "2026-03-15T09:05:00Z",
    },
    {
      eval_run_id: RUN_HISTORY_ID,
      suite_id: SUITE_IMPORTED_ID,
      transport_profile_id: HTTP_DESTINATION_ID,
      transport_profile_ids: [HTTP_DESTINATION_ID],
      destination_count: 1,
      destinations: [
        {
          destination_index: 0,
          transport_profile_id: HTTP_DESTINATION_ID,
          label: "Billing HTTP Bot",
        },
      ],
      status: "complete",
      trigger_source: "schedule",
      schedule_id: "sched_billing_daily",
      triggered_by: "scheduler",
      prompt_count: 2,
      case_count: 2,
      total_pairs: 4,
      dispatched_count: 4,
      completed_count: 4,
      failed_count: 0,
      created_at: "2026-03-14T09:00:00Z",
      updated_at: "2026-03-14T09:04:00Z",
    },
  ];
  const runDetailBody = (runId: string) =>
    runId === RUN_HISTORY_ID
      ? {
          eval_run_id: RUN_HISTORY_ID,
          suite_id: SUITE_IMPORTED_ID,
          transport_profile_id: HTTP_DESTINATION_ID,
          transport_profile_ids: [HTTP_DESTINATION_ID],
          endpoint_at_start: "https://bot.internal/http",
          headers_at_start: {},
          direct_http_config_at_start: {
            method: "POST",
            request_content_type: "json",
            request_text_field: "message",
            response_text_field: "reply",
          },
          destinations: [
            {
              destination_index: 0,
              transport_profile_id: HTTP_DESTINATION_ID,
              label: "Billing HTTP Bot",
              protocol: "http",
              endpoint_at_start: "https://bot.internal/http",
              headers_at_start: {},
              direct_http_config_at_start: {
                method: "POST",
                request_content_type: "json",
                request_text_field: "message",
                response_text_field: "reply",
              },
            },
          ],
          trigger_source: "schedule",
          schedule_id: "sched_billing_daily",
          triggered_by: "scheduler",
          status: "complete",
          prompt_count: 2,
          case_count: 2,
          total_pairs: 4,
          dispatched_count: 4,
          completed_count: 4,
          failed_count: 0,
          created_at: "2026-03-14T09:00:00Z",
          updated_at: "2026-03-14T09:04:00Z",
        }
      : {
          eval_run_id: RUN_ID,
          suite_id: SUITE_IMPORTED_ID,
          transport_profile_id: HTTP_DESTINATION_ID,
          transport_profile_ids: [HTTP_DESTINATION_ID, HTTP_DESTINATION_B_ID],
          endpoint_at_start: "https://bot.internal/http",
          headers_at_start: {},
          direct_http_config_at_start: {
            method: "POST",
            request_content_type: "json",
            request_text_field: "message",
            response_text_field: "reply",
          },
          destinations: [
            {
              destination_index: 0,
              transport_profile_id: HTTP_DESTINATION_ID,
              label: "Billing HTTP Bot",
              protocol: "http",
              endpoint_at_start: "https://bot.internal/http",
              headers_at_start: {},
              direct_http_config_at_start: {
                method: "POST",
                request_content_type: "json",
                request_text_field: "message",
                response_text_field: "reply",
              },
            },
            {
              destination_index: 1,
              transport_profile_id: HTTP_DESTINATION_B_ID,
              label: "Billing HTTP Bot B",
              protocol: "http",
              endpoint_at_start: "https://bot-b.internal/http",
              headers_at_start: {},
              direct_http_config_at_start: {
                method: "POST",
                request_content_type: "json",
                request_text_field: "message",
                response_text_field: "reply",
              },
            },
          ],
          trigger_source: "manual",
          schedule_id: null,
          triggered_by: "user_e2e",
          status: runStatus,
          prompt_count: 2,
          case_count: 2,
          total_pairs: 8,
          dispatched_count: 6,
          completed_count: 5,
          failed_count: 1,
          created_at: "2026-03-15T09:00:00Z",
          updated_at: "2026-03-15T09:05:00Z",
        };
  const runProgressBody = (runId: string) =>
    runId === RUN_HISTORY_ID
      ? {
          eval_run_id: RUN_HISTORY_ID,
          status: "complete",
          prompt_count: 2,
          case_count: 2,
          total_pairs: 4,
          dispatched_count: 4,
          completed_count: 4,
          failed_count: 0,
          progress_fraction: 1,
          updated_at: "2026-03-14T09:04:00Z",
        }
      : {
          eval_run_id: RUN_ID,
          status: runStatus,
          prompt_count: 2,
          case_count: 2,
          total_pairs: 8,
          dispatched_count: 6,
          completed_count: 5,
          failed_count: 1,
          progress_fraction: 0.75,
          updated_at: "2026-03-15T09:05:00Z",
        };
  const runReportBody = (runId: string, currentSearchParams: URLSearchParams) =>
    runId === RUN_HISTORY_ID
      ? {
          eval_run_id: RUN_HISTORY_ID,
          suite_id: SUITE_IMPORTED_ID,
          status: "complete",
          total_pairs: 4,
          filters: {
            prompt_id: currentSearchParams.get("prompt_id"),
            assertion_type: currentSearchParams.get("assertion_type"),
            tag: currentSearchParams.get("tag"),
            status: currentSearchParams.get("status"),
            destination_index:
              currentSearchParams.get("destination_index") !== null
                ? Number(currentSearchParams.get("destination_index"))
                : null,
          },
          total_results: 1,
          passed_results: 1,
          failed_results: 0,
          assertion_type_breakdown: [
            {
              assertion_type: "contains",
              total_results: 1,
              passed_results: 1,
              failed_results: 0,
            },
          ],
          failing_prompt_variants: [],
          tag_failure_clusters: [],
          exemplar_failures: [],
        }
      : null;
  const runResultsBody = (runId: string, currentSearchParams: URLSearchParams) =>
    runId === RUN_HISTORY_ID
      ? {
          eval_run_id: RUN_HISTORY_ID,
          filters: {
            prompt_id: currentSearchParams.get("prompt_id"),
            assertion_type: currentSearchParams.get("assertion_type"),
            tag: currentSearchParams.get("tag"),
            status: currentSearchParams.get("status"),
            destination_index:
              currentSearchParams.get("destination_index") !== null
                ? Number(currentSearchParams.get("destination_index"))
                : null,
          },
          items: [historyResult],
          next_cursor: null,
        }
      : null;
  const runMatrixBody = (runId: string) =>
    runId === RUN_HISTORY_ID
      ? {
          eval_run_id: RUN_HISTORY_ID,
          suite_id: SUITE_IMPORTED_ID,
          status: "complete",
          total_pairs: 4,
          destinations: [
            {
              destination_index: 0,
              transport_profile_id: HTTP_DESTINATION_ID,
              label: "Billing HTTP Bot",
              protocol: "http",
              pass_rate: 1,
              total_pairs: 4,
              passed: 4,
              failed: 0,
              errors: 0,
              avg_latency_ms: 430,
            },
          ],
          prompt_groups: [
            {
              prompt_id: `${SUITE_IMPORTED_ID}_prompt_helpful`,
              prompt_label: "helpful",
              prompt_text: "Answer clearly: {{question}}",
              rows: [
                {
                  prompt_id: `${SUITE_IMPORTED_ID}_prompt_helpful`,
                  case_id: `${SUITE_IMPORTED_ID}_case_refund`,
                  case_description: "Refund policy",
                  tags_json: ["billing", "smoke-test"],
                  cells: [
                    {
                      destination_index: 0,
                      transport_profile_id: HTTP_DESTINATION_ID,
                      destination_label: "Billing HTTP Bot",
                      status: "passed",
                      artifact_eval_result_id: RESULT_HISTORY_ID,
                      response_snippet: "Refunds are available within 30 days.",
                      latency_ms: 430,
                      assertion_results: [
                        {
                          assertion_index: 0,
                          assertion_type: "contains",
                          passed: true,
                          failure_reason: null,
                        },
                      ],
                    },
                  ],
                },
              ],
            },
          ],
        }
      : null;

  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname, searchParams } = url;
    const method = request.method();

    if (await maybeMockIdentityRoute(route, { pathname, method }, { role })) {
      return;
    }

    if (pathname === "/features" && method === "GET") {
      return ok(route, {
        destinations_enabled: true,
      });
    }

    if (pathname === "/providers/available" && method === "GET") {
      return ok(route, {
        items: [
          {
            provider_id: "openai:gpt-4o-mini",
            vendor: "openai",
            model: "gpt-4o-mini",
            capability: "llm",
            runtime_scopes: ["api"],
            credential_source: "env",
            configured: true,
            availability_status: "available",
            supports_tenant_credentials: false,
          },
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
        ],
      });
    }

    if (pathname === "/destinations/" && method === "GET") {
      return ok(route, [
        {
          destination_id: HTTP_DESTINATION_ID,
          transport_profile_id: HTTP_DESTINATION_ID,
          name: "Billing HTTP Bot",
          protocol: "http",
          endpoint: "https://bot.internal/http",
          default_dial_target: "https://bot.internal/http",
          direct_http_config: {
            method: "POST",
            request_content_type: "json",
            request_text_field: "message",
            response_text_field: "reply",
          },
          is_active: true,
          in_use: false,
          active_schedule_count: 0,
          active_pack_run_count: 0,
          created_at: "2026-03-15T08:00:00Z",
          updated_at: "2026-03-15T08:30:00Z",
        },
        {
          destination_id: HTTP_DESTINATION_B_ID,
          transport_profile_id: HTTP_DESTINATION_B_ID,
          name: "Billing HTTP Bot B",
          protocol: "http",
          endpoint: "https://bot-b.internal/http",
          default_dial_target: "https://bot-b.internal/http",
          direct_http_config: {
            method: "POST",
            request_content_type: "json",
            request_text_field: "message",
            response_text_field: "reply",
          },
          is_active: true,
          in_use: false,
          active_schedule_count: 0,
          active_pack_run_count: 0,
          created_at: "2026-03-15T08:00:00Z",
          updated_at: "2026-03-15T08:30:00Z",
        },
        {
          destination_id: "dest_sip_ignore",
          transport_profile_id: "dest_sip_ignore",
          name: "SIP Trunk",
          protocol: "sip",
          endpoint: "sip:test@example.com",
          is_active: true,
          in_use: false,
          active_schedule_count: 0,
          active_pack_run_count: 0,
          created_at: "2026-03-15T08:00:00Z",
          updated_at: "2026-03-15T08:30:00Z",
        },
      ]);
    }

    if (pathname === "/grai/suites" && method === "GET") {
      return ok(route, suites);
    }

    if (pathname === `/grai/suites/${SUITE_IMPORTED_ID}/runs` && method === "GET") {
      return ok(route, importedSuiteHistory());
    }

    if (
      (pathname === `/grai/suites/${SUITE_NATIVE_ID}/runs` ||
        pathname === `/grai/suites/${SUITE_CREATED_ID}/runs` ||
        pathname === `/grai/suites/${SUITE_IMPORTED_FROM_DIALOG_ID}/runs`) &&
      method === "GET"
    ) {
      return ok(route, []);
    }

    if (pathname === "/grai/suites" && method === "POST") {
      const body = request.postDataJSON() as { name: string; description?: string | null };
      const createdSummary = suiteSummary(SUITE_CREATED_ID, body.name, {
        description: body.description ?? null,
      });
      const createdDetail = suiteDetail(SUITE_CREATED_ID, body.name, {
        description: body.description ?? null,
      });
      suites.unshift(createdSummary);
      suiteDetails.set(SUITE_CREATED_ID, createdDetail);
      return ok(route, createdDetail, 201);
    }

    if (pathname === "/grai/suites/import" && method === "POST") {
      const body = request.postDataJSON() as { name?: string | null };
      const createdName = body.name || "Imported from dialog";
      const createdSummary = suiteSummary(SUITE_IMPORTED_FROM_DIALOG_ID, createdName, {
        description: "Imported from promptfoo YAML",
        imported: true,
      });
      const createdDetail = suiteDetail(SUITE_IMPORTED_FROM_DIALOG_ID, createdName, {
        description: "Imported from promptfoo YAML",
        sourceYaml: "description: imported suite",
      });
      suites.unshift(createdSummary);
      suiteDetails.set(SUITE_IMPORTED_FROM_DIALOG_ID, createdDetail);
      return ok(route, createdDetail, 201);
    }

    if (pathname.startsWith("/grai/suites/") && method === "GET") {
      const suiteId = pathname.split("/").pop() ?? "";
      const detail = suiteDetails.get(suiteId);
      if (!detail) {
        return ok(route, { detail: "suite not found" }, 404);
      }
      return ok(route, detail);
    }

    if (pathname === "/grai/runs" && method === "POST") {
      const body = request.postDataJSON() as {
        transport_profile_id?: string | null;
        transport_profile_ids: string[];
      };
      expect(body.transport_profile_ids).toEqual([HTTP_DESTINATION_ID, HTTP_DESTINATION_B_ID]);
      runStatus = "running";
      return ok(route, {
        eval_run_id: RUN_ID,
        suite_id: SUITE_IMPORTED_ID,
        transport_profile_id: HTTP_DESTINATION_ID,
        transport_profile_ids: [HTTP_DESTINATION_ID, HTTP_DESTINATION_B_ID],
        endpoint_at_start: "https://bot.internal/http",
        headers_at_start: {},
        direct_http_config_at_start: {
          method: "POST",
          request_content_type: "json",
          request_text_field: "message",
          response_text_field: "reply",
        },
        destinations: [
          {
            destination_index: 0,
            transport_profile_id: HTTP_DESTINATION_ID,
            label: "Billing HTTP Bot",
            protocol: "http",
            endpoint_at_start: "https://bot.internal/http",
            headers_at_start: {},
            direct_http_config_at_start: {
              method: "POST",
              request_content_type: "json",
              request_text_field: "message",
              response_text_field: "reply",
            },
          },
          {
            destination_index: 1,
            transport_profile_id: HTTP_DESTINATION_B_ID,
            label: "Billing HTTP Bot B",
            protocol: "http",
            endpoint_at_start: "https://bot-b.internal/http",
            headers_at_start: {},
            direct_http_config_at_start: {
              method: "POST",
              request_content_type: "json",
              request_text_field: "message",
              response_text_field: "reply",
            },
          },
        ],
        trigger_source: "manual",
        schedule_id: null,
        triggered_by: "user_e2e",
        status: runStatus,
        prompt_count: 2,
        case_count: 2,
        total_pairs: 8,
        dispatched_count: 4,
        completed_count: 1,
        failed_count: 1,
        created_at: "2026-03-15T09:00:00Z",
        updated_at: "2026-03-15T09:02:00Z",
      }, 202);
    }

    if ((pathname === `/grai/runs/${RUN_ID}` || pathname === `/grai/runs/${RUN_HISTORY_ID}`) && method === "GET") {
      const runId = pathname.split("/").pop() ?? "";
      return ok(route, runDetailBody(runId));
    }

    if (
      (pathname === `/grai/runs/${RUN_ID}/progress` || pathname === `/grai/runs/${RUN_HISTORY_ID}/progress`) &&
      method === "GET"
    ) {
      const runId = pathname.split("/")[3] ?? "";
      return ok(route, runProgressBody(runId));
    }

    if (
      (pathname === `/grai/runs/${RUN_ID}/report` || pathname === `/grai/runs/${RUN_HISTORY_ID}/report`) &&
      method === "GET"
    ) {
      const runId = pathname.split("/")[3] ?? "";
      if (runId === RUN_HISTORY_ID) {
        return ok(route, runReportBody(runId, searchParams));
      }
      const promptId = searchParams.get("prompt_id");
      const status = searchParams.get("status");
      const destinationIndex = searchParams.get("destination_index");
      const exemplarFailures =
        promptId === `${SUITE_IMPORTED_ID}_prompt_brief` || status === "passed" ? [] : [resultOne];
      return ok(route, {
        eval_run_id: RUN_ID,
        suite_id: SUITE_IMPORTED_ID,
        status: runStatus,
        total_pairs: 4,
        filters: {
          prompt_id: promptId,
          assertion_type: searchParams.get("assertion_type"),
          tag: searchParams.get("tag"),
          status,
          destination_index: destinationIndex !== null ? Number(destinationIndex) : null,
        },
        total_results: status === "passed" ? 1 : 2,
        passed_results: status === "failed" ? 0 : 1,
        failed_results: status === "passed" ? 0 : 1,
        assertion_type_breakdown: [
          {
            assertion_type: "contains",
            total_results: 1,
            passed_results: 0,
            failed_results: 1,
          },
          {
            assertion_type: "llm-rubric",
            total_results: 1,
            passed_results: 1,
            failed_results: 0,
          },
        ],
        failing_prompt_variants: [
          {
            prompt_id: `${SUITE_IMPORTED_ID}_prompt_helpful`,
            prompt_label: "helpful",
            failure_count: 1,
            failed_pairs: 1,
          },
        ],
        tag_failure_clusters: [
          {
            tag: "billing",
            failure_count: 1,
            failed_pairs: 1,
          },
        ],
        exemplar_failures: exemplarFailures,
      });
    }

    if (
      (pathname === `/grai/runs/${RUN_ID}/results` || pathname === `/grai/runs/${RUN_HISTORY_ID}/results`) &&
      method === "GET"
    ) {
      const runId = pathname.split("/")[3] ?? "";
      if (runId === RUN_HISTORY_ID) {
        return ok(route, runResultsBody(runId, searchParams));
      }
      const cursor = searchParams.get("cursor");
      if (cursor === "cursor-2") {
        return ok(route, {
          eval_run_id: RUN_ID,
          filters: {
            prompt_id: searchParams.get("prompt_id"),
            assertion_type: searchParams.get("assertion_type"),
            tag: searchParams.get("tag"),
            status: searchParams.get("status"),
            destination_index: searchParams.get("destination_index") !== null
              ? Number(searchParams.get("destination_index"))
              : null,
          },
          items: [resultTwo],
          next_cursor: null,
        });
      }
      return ok(route, {
        eval_run_id: RUN_ID,
        filters: {
          prompt_id: searchParams.get("prompt_id"),
          assertion_type: searchParams.get("assertion_type"),
          tag: searchParams.get("tag"),
          status: searchParams.get("status"),
          destination_index: searchParams.get("destination_index") !== null
            ? Number(searchParams.get("destination_index"))
            : null,
        },
        items: [resultOne],
        next_cursor: "cursor-2",
      });
    }

    if (
      (pathname === `/grai/runs/${RUN_ID}/matrix` || pathname === `/grai/runs/${RUN_HISTORY_ID}/matrix`) &&
      method === "GET"
    ) {
      const runId = pathname.split("/")[3] ?? "";
      if (runId === RUN_HISTORY_ID) {
        return ok(route, runMatrixBody(runId));
      }
      return ok(route, {
        eval_run_id: RUN_ID,
        suite_id: SUITE_IMPORTED_ID,
        status: runStatus,
        total_pairs: 8,
        destinations: [
          {
            destination_index: 0,
            transport_profile_id: HTTP_DESTINATION_ID,
            label: "Billing HTTP Bot",
            protocol: "http",
            pass_rate: 0.75,
            total_pairs: 4,
            passed: 3,
            failed: 1,
            errors: 0,
            avg_latency_ms: 610,
          },
          {
            destination_index: 1,
            transport_profile_id: HTTP_DESTINATION_B_ID,
            label: "Billing HTTP Bot B",
            protocol: "http",
            pass_rate: 0.25,
            total_pairs: 4,
            passed: 1,
            failed: 2,
            errors: 0,
            avg_latency_ms: 780,
          },
        ],
        prompt_groups: [
          {
            prompt_id: `${SUITE_IMPORTED_ID}_prompt_helpful`,
            prompt_label: "helpful",
            prompt_text: "Answer clearly: {{question}}",
            rows: [
              {
                prompt_id: `${SUITE_IMPORTED_ID}_prompt_helpful`,
                case_id: `${SUITE_IMPORTED_ID}_case_refund`,
                case_description: "Refund policy",
                tags_json: ["billing", "smoke-test"],
                cells: [
                  {
                    destination_index: 0,
                    transport_profile_id: HTTP_DESTINATION_ID,
                    destination_label: "Billing HTTP Bot",
                    status: "failed",
                    artifact_eval_result_id: RESULT_ONE_ID,
                    response_snippet: "Response missed refund guidance",
                    latency_ms: 610,
                    assertion_results: [
                      {
                        assertion_index: 0,
                        assertion_type: "contains",
                        passed: false,
                        failure_reason: "Response missed refund guidance",
                      },
                    ],
                  },
                  {
                    destination_index: 1,
                    transport_profile_id: HTTP_DESTINATION_B_ID,
                    destination_label: "Billing HTTP Bot B",
                    status: "passed",
                    artifact_eval_result_id: RESULT_TWO_ID,
                    response_snippet: "Open billing settings and choose cancel subscription.",
                    latency_ms: 540,
                    assertion_results: [
                      {
                        assertion_index: 0,
                        assertion_type: "contains",
                        passed: true,
                        failure_reason: null,
                      },
                    ],
                  },
                ],
              },
              {
                prompt_id: `${SUITE_IMPORTED_ID}_prompt_helpful`,
                case_id: `${SUITE_IMPORTED_ID}_case_cancel`,
                case_description: "Cancel subscription",
                tags_json: ["account", "retention"],
                cells: [
                  {
                    destination_index: 0,
                    transport_profile_id: HTTP_DESTINATION_ID,
                    destination_label: "Billing HTTP Bot",
                    status: "pending",
                    artifact_eval_result_id: null,
                    response_snippet: null,
                    latency_ms: null,
                    assertion_results: [],
                  },
                  {
                    destination_index: 1,
                    transport_profile_id: HTTP_DESTINATION_B_ID,
                    destination_label: "Billing HTTP Bot B",
                    status: "pending",
                    artifact_eval_result_id: null,
                    response_snippet: null,
                    latency_ms: null,
                    assertion_results: [],
                  },
                ],
              },
            ],
          },
          {
            prompt_id: `${SUITE_IMPORTED_ID}_prompt_brief`,
            prompt_label: "brief",
            prompt_text: "Reply in one sentence: {{question}}",
            rows: [
              {
                prompt_id: `${SUITE_IMPORTED_ID}_prompt_brief`,
                case_id: `${SUITE_IMPORTED_ID}_case_refund`,
                case_description: "Refund policy",
                tags_json: ["billing", "smoke-test"],
                cells: [
                  {
                    destination_index: 0,
                    transport_profile_id: HTTP_DESTINATION_ID,
                    destination_label: "Billing HTTP Bot",
                    status: "passed",
                    artifact_eval_result_id: RESULT_ONE_ID,
                    response_snippet: "Refunds are available within 30 days.",
                    latency_ms: 400,
                    assertion_results: [
                      {
                        assertion_index: 0,
                        assertion_type: "contains",
                        passed: true,
                        failure_reason: null,
                      },
                    ],
                  },
                  {
                    destination_index: 1,
                    transport_profile_id: HTTP_DESTINATION_B_ID,
                    destination_label: "Billing HTTP Bot B",
                    status: "failed",
                    artifact_eval_result_id: RESULT_TWO_ID,
                    response_snippet: "This answer skipped the refund policy.",
                    latency_ms: 780,
                    assertion_results: [
                      {
                        assertion_index: 0,
                        assertion_type: "llm-rubric",
                        passed: false,
                        failure_reason: "Response skipped the expected policy detail.",
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      });
    }

    if (pathname === `/grai/runs/${RUN_ID}/results/${RESULT_ONE_ID}/artifact` && method === "GET") {
      return ok(route, {
        prompt_id: `${SUITE_IMPORTED_ID}_prompt_helpful`,
        case_id: `${SUITE_IMPORTED_ID}_case_refund`,
        prompt_text: "Answer clearly: What is the refund policy?",
        vars_json: { question: "What is the refund policy?" },
        response_text: "You can request a refund within 30 days.",
        assertions: [
          {
            assertion_type: "contains",
            raw_value: "refund",
            passed: false,
          },
        ],
      });
    }

    if (pathname === `/grai/runs/${RUN_ID}/results/${RESULT_TWO_ID}/artifact` && method === "GET") {
      return ok(route, {
        prompt_id: `${SUITE_IMPORTED_ID}_prompt_brief`,
        case_id: `${SUITE_IMPORTED_ID}_case_cancel`,
        prompt_text: "Reply in one sentence: How do I cancel?",
        vars_json: { question: "How do I cancel?" },
        response_text: "Open billing settings and choose cancel subscription.",
        assertions: [
          {
            assertion_type: "llm-rubric",
            raw_value: "clarity",
            passed: true,
          },
        ],
      });
    }

    if (pathname === `/grai/runs/${RUN_ID}/cancel` && method === "POST") {
      runStatus = "cancelled";
      return ok(route, {
        eval_run_id: RUN_ID,
        applied: true,
        status: runStatus,
        reason: "cancel_requested",
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke grai evals page", () => {
  test("editor can create and import suites from the eval surface", async ({ page }) => {
    await installAuthSession(page, { role: "editor" });
    await mockGraiApi(page, "editor");

    await page.goto("/grai-evals");

    await expect(page.getByTestId("grai-evals-page")).toBeVisible();
    await expect(page.getByTestId("grai-provider-access-card")).toContainText(
      "anthropic:claude-sonnet-4-6"
    );
    await expect(page.getByTestId(`grai-suite-card-${SUITE_IMPORTED_ID}`)).toBeVisible();

    await page.getByTestId("grai-create-suite-button").click();
    await page.getByTestId("grai-suite-name").fill("Card-created suite");
    await page.getByTestId("grai-suite-description").fill("Created directly from the web UI");
    await page.getByTestId("grai-suite-submit").click();

    await expect(page.getByRole("heading", { name: "Card-created suite" })).toBeVisible();
    await expect(page.getByTestId(`grai-suite-card-${SUITE_CREATED_ID}`)).toBeVisible();

    await page.getByTestId("grai-import-button").click();
    await page.getByTestId("grai-import-name").fill("Imported from dialog");
    await page.getByTestId("grai-import-yaml").fill(
      "description: Billing smoke\nprompts:\n  - raw: Answer clearly: {{question}}\n"
    );
    await page.getByTestId("grai-import-submit").click();

    await expect(page.getByRole("heading", { name: "Imported from dialog" })).toBeVisible();
    await expect(page.getByTestId(`grai-suite-card-${SUITE_IMPORTED_FROM_DIALOG_ID}`)).toBeVisible();
  });

  test("operator can launch runs, page through results, open artifacts, and clear run context on suite switch", async ({
    page,
  }) => {
    await installAuthSession(page, { role: "operator" });
    await mockGraiApi(page, "operator");

    await page.goto("/grai-evals");

    await page.getByTestId(`grai-run-transport-option-${HTTP_DESTINATION_ID}`).check();
    await page.getByTestId(`grai-run-transport-option-${HTTP_DESTINATION_B_ID}`).check();
    await page.getByTestId("grai-run-launch-button").click();

    await expect(page.getByTestId("grai-run-progress-card")).toBeVisible();
    await expect(page.getByTestId("grai-matrix-card")).toBeVisible();
    await expect(page.getByTestId(`grai-matrix-summary-0`)).toContainText("75%");
    await expect(
      page.getByTestId(
        `grai-matrix-cell-${SUITE_IMPORTED_ID}_prompt_helpful-${SUITE_IMPORTED_ID}_case_cancel-0`
      )
    ).toContainText("pending");
    await expect(page.getByTestId("grai-report-card")).toContainText("1 failed results / 2 total");
    await expect(page.getByTestId(`grai-result-row-${RESULT_ONE_ID}`)).toBeVisible();

    await page.getByTestId("grai-report-filter-destination").selectOption("0");
    await expect(page.getByTestId("grai-report-card")).toContainText("1 failed results / 2 total");

    await page.getByTestId("grai-results-load-more").click();
    await expect(page.getByTestId(`grai-result-row-${RESULT_ONE_ID}`)).toBeVisible();
    await expect(page.getByTestId(`grai-result-row-${RESULT_TWO_ID}`)).toBeVisible();

    await page.getByTestId(`grai-matrix-open-${RESULT_ONE_ID}`).first().click();
    await expect(page.getByRole("heading", { name: "Exemplar Request / Response" })).toBeVisible();
    await expect(page.getByText("You can request a refund within 30 days.")).toBeVisible();
    await page.getByRole("button", { name: "Close grai artifact dialog" }).click();

    await page.getByTestId("grai-run-cancel-button").click();
    await expect(page.getByTestId("grai-run-progress-card")).toContainText("cancelled");

    await page.getByTestId(`grai-suite-card-${SUITE_NATIVE_ID}`).click();
    await expect(page.getByRole("heading", { name: "Native account suite" })).toBeVisible();
    await expect(page.getByTestId("grai-run-progress-card")).toHaveCount(0);
    await expect(page.getByTestId("grai-report-card")).toHaveCount(0);
  });

  test("history panel reopens older runs and deep links canonicalize suite selection", async ({
    page,
  }) => {
    await installAuthSession(page, { role: "operator" });
    await mockGraiApi(page, "operator");

    await page.goto(`/grai-evals?run=${RUN_HISTORY_ID}`);

    await expect(page).toHaveURL(
      new RegExp(
        `(?:suite=${SUITE_IMPORTED_ID}.*run=${RUN_HISTORY_ID}|run=${RUN_HISTORY_ID}.*suite=${SUITE_IMPORTED_ID})`
      )
    );
    await expect(page.getByRole("heading", { name: "Imported billing suite" })).toBeVisible();
    await expect(page.getByTestId("grai-run-progress-card")).toContainText(RUN_HISTORY_ID);
    await expect(page.getByTestId("grai-run-history-card")).toBeVisible();
    await expect(page.getByTestId(`grai-run-history-${RUN_HISTORY_ID}`)).toContainText("complete");
    await expect(page.getByTestId(`grai-run-history-${RUN_HISTORY_ID}`)).toContainText(
      "Billing HTTP Bot"
    );

    await page.getByTestId(`grai-run-history-${RUN_ID}`).click();

    await expect(page).toHaveURL(
      new RegExp(`(?:suite=${SUITE_IMPORTED_ID}.*run=${RUN_ID}|run=${RUN_ID}.*suite=${SUITE_IMPORTED_ID})`)
    );
    await expect(page.getByTestId("grai-run-progress-card")).toContainText(RUN_ID);
    await expect(page.getByTestId(`grai-run-history-${RUN_ID}`)).toContainText("running");
  });

  test("viewer gets read-only access to the grai eval surface", async ({ page }) => {
    await installAuthSession(page, { role: "viewer" });
    await mockGraiApi(page, "viewer");

    await page.goto("/grai-evals");

    await expect(page.getByTestId("grai-evals-page")).toBeVisible();
    await expect(page.getByTestId("grai-import-button")).toHaveCount(0);
    await expect(page.getByTestId("grai-create-suite-button")).toHaveCount(0);

    await page.getByTestId(`grai-run-transport-option-${HTTP_DESTINATION_ID}`).check();
    await expect(page.getByTestId("grai-run-launch-button")).toBeDisabled();
    await expect(
      page.getByTestId("grai-run-launch-card").getByText("Run launch requires operator role or above.")
    ).toBeVisible();
  });
});
