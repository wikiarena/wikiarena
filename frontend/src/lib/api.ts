export type SolvePathMode = "single" | "all_shortest";

export interface MetaResponse {
  service_version: string;
  snapshot_id: string;
  dump_date: string;
  node_count: number;
  edge_count: number;
  default_path_mode: SolvePathMode;
  supported_path_modes: SolvePathMode[];
}

export interface SolveResponse {
  snapshot_id: string;
  start_title: string;
  target_title: string;
  path_length: number | null;
  paths: string[][];
  solve_ms: number;
  pages_visited: number;
  links_scanned: number;
}

export interface RandomPageTitlesResponse {
  snapshot_id: string;
  titles: string[];
}

export interface TitleValidationResponse {
  snapshot_id: string;
  query_title: string;
  exists: boolean;
  canonical_title: string | null;
}

export interface RaceParticipantRequest {
  participant_id?: string;
  display_name?: string;
  provider: string;
  model: string;
  settings?: Record<string, unknown>;
}

export interface CreateRaceRequest {
  start_title: string;
  target_title: string;
  participants: RaceParticipantRequest[];
  benchmark_id?: string;
  max_moves?: number;
  navigation_backend?: "graph" | "live";
  solver_backend?: "local" | "none";
}

export interface RaceCreatedResponse {
  race_id: string;
  status: string;
  stream_url: string;
  events_url: string;
  race_url: string;
}

interface ErrorResponse {
  code?: string;
  message?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

const LOCAL_API_BASE_URL = "http://localhost:8000";
const PRODUCTION_API_BASE_URL = "https://api.wikiarena.org";

function resolveApiBaseUrl(): string {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL;
  if (configuredBaseUrl && configuredBaseUrl.trim()) {
    return configuredBaseUrl.trim().replace(/\/$/, "");
  }

  const isLocalHost =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1" ||
    window.location.hostname.startsWith("192.168.") ||
    window.location.port === "3000";

  return isLocalHost ? LOCAL_API_BASE_URL : PRODUCTION_API_BASE_URL;
}

const apiBaseUrl = resolveApiBaseUrl();

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    let errorPayload: ErrorResponse | null = null;
    try {
      errorPayload = (await response.json()) as ErrorResponse;
    } catch {
      errorPayload = null;
    }

    const message =
      errorPayload?.message ??
      `Request failed with status ${response.status}.`;

    throw new ApiError(
      message,
      response.status,
      errorPayload?.code ?? null,
    );
  }

  return (await response.json()) as T;
}

export async function loadMeta(): Promise<MetaResponse> {
  return requestJson<MetaResponse>("/v1/meta");
}

export async function solvePath(
  startTitle: string,
  targetTitle: string,
  pathMode: SolvePathMode,
): Promise<SolveResponse> {
  return requestJson<SolveResponse>("/v1/solve", {
    method: "POST",
    body: JSON.stringify({
      start_title: startTitle,
      target_title: targetTitle,
      path_mode: pathMode,
    }),
  });
}

export async function loadRandomPageTitles(count: number): Promise<RandomPageTitlesResponse> {
  const searchParams = new URLSearchParams({
    count: String(count),
  });
  return requestJson<RandomPageTitlesResponse>(`/v1/random-page-titles?${searchParams.toString()}`);
}

export async function validateTitle(title: string): Promise<TitleValidationResponse> {
  const searchParams = new URLSearchParams({
    title,
  });
  return requestJson<TitleValidationResponse>(`/v1/title-validation?${searchParams.toString()}`);
}

export async function createRace(request: CreateRaceRequest): Promise<RaceCreatedResponse> {
  return requestJson<RaceCreatedResponse>("/v1/races", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getApiBaseUrl(): string {
  return apiBaseUrl;
}

export function getWebSocketBaseUrl(): string {
  if (apiBaseUrl.startsWith("https://")) {
    return `wss://${apiBaseUrl.slice("https://".length)}`;
  }
  if (apiBaseUrl.startsWith("http://")) {
    return `ws://${apiBaseUrl.slice("http://".length)}`;
  }
  return apiBaseUrl;
}
