export interface EventEnvelope {
  event_id: string;
  event_type: "run_started" | "step_attempt_recorded" | "move_committed" | "position_solver_facts_recorded" | "run_terminated";
  benchmark_id: string;
  race_id: string;
  run_id: string;
  sequence: number;
  occurred_at: string;
  payload: Record<string, unknown>;
  error?: Record<string, unknown> | null;
}

export interface StoredRaceEvent {
  stream_sequence: number;
  event: EventEnvelope;
}

export interface RaceParticipantSummary {
  participant_id: string;
  display_name: string;
  provider: string;
  model: string;
  run_id: string;
}

export interface RaceMetadata {
  race_id: string;
  benchmark_id: string;
  task_id: string;
  start_title: string;
  target_title: string;
  participants: RaceParticipantSummary[];
  status: "pending" | "running" | "completed" | "failed";
  error_message?: string | null;
}

export interface RaceStateResponse {
  metadata: RaceMetadata;
  latest_stream_sequence: number;
  events: StoredRaceEvent[];
  run_results?: RunResultSummary[];
}

export interface RunResultSummary {
  run_id: string;
  terminal_outcome: string;
  termination_reason: string;
  total_step_attempts: number;
  total_committed_moves: number;
  total_invalid_attempts: number;
  estimated_cost_usd: number;
  step_attempts?: Array<{
    model_metrics?: {
      total_tokens?: number;
      response_time_ms?: number;
    } | null;
  }>;
}

export interface SolverFacts {
  page_title: string;
  target_page_title: string;
  shortest_path_length: number | null;
  shortest_paths: string[][];
  shortest_next_hop_titles: string[];
  solver_snapshot_id?: string | null;
}

export interface RaceMove {
  moveIndex: number;
  fromPageTitle: string;
  toPageTitle: string;
  distanceBefore?: number | null;
  distanceAfter?: number | null;
}

export interface ParticipantTrack {
  participantId: string;
  displayName: string;
  provider: string;
  model: string;
  runId: string;
  color: string;
  status: "pending" | "running" | "completed";
  currentPageTitle: string;
  currentDistance?: number | null;
  terminalOutcome?: string;
  terminationReason?: string;
  totalStepAttempts?: number;
  totalCommittedMoves?: number;
  totalInvalidAttempts?: number;
  estimatedCostUsd?: number;
  totalModelTokens?: number;
  totalApiTimeMs?: number;
  moves: RaceMove[];
  solverFactsByPage: Map<string, SolverFacts>;
}

export interface RaceViewState {
  metadata: RaceMetadata | null;
  latestStreamSequence: number;
  tracksByRunId: Map<string, ParticipantTrack>;
  eventLog: StoredRaceEvent[];
  renderingMode: "live" | "stepping";
  viewingPageIndex: number;
}
