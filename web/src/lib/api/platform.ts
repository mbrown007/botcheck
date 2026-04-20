import useSWR from "swr";

import { fetcher } from "./fetcher";
import type { PlatformHealthResponse } from "./types";

export function usePlatformHealth() {
  return useSWR<PlatformHealthResponse>("/health", fetcher, {
    refreshInterval: 60_000,
  });
}
