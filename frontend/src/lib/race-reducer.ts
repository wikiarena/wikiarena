import type { ParticipantTrack, RaceMetadata, RaceViewState, SolverFacts, StoredRaceEvent } from "./race-types";

const TRACK_COLORS = ["#111111", "#8f8f8f", "#0645ad", "#ffb000", "#785ef0", "#0b7285"];

export function createRaceViewState(metadata: RaceMetadata | null = null): RaceViewState {
  const tracksByRunId = new Map<string, ParticipantTrack>();
  if (metadata !== null) {
    metadata.participants.forEach((participant, index) => {
      tracksByRunId.set(participant.run_id, {
        participantId: participant.participant_id,
        displayName: participant.display_name,
        provider: participant.provider,
        model: participant.model,
        runId: participant.run_id,
        color: TRACK_COLORS[index % TRACK_COLORS.length],
        status: "pending",
        currentPageTitle: metadata.start_title,
        currentDistance: undefined,
        moves: [],
        solverFactsByPage: new Map<string, SolverFacts>(),
      });
    });
  }
  return {
    metadata,
    latestStreamSequence: 0,
    tracksByRunId,
    eventLog: [],
    renderingMode: "live",
    viewingPageIndex: 0,
  };
}

export function reduceStoredRaceEvent(state: RaceViewState, storedEvent: StoredRaceEvent): RaceViewState {
  if (storedEvent.stream_sequence <= state.latestStreamSequence) {
    return state;
  }

  const track = state.tracksByRunId.get(storedEvent.event.run_id);
  if (track === undefined) {
    return {
      ...state,
      latestStreamSequence: storedEvent.stream_sequence,
      eventLog: [...state.eventLog, storedEvent],
    };
  }

  const nextTracks = new Map(state.tracksByRunId);
  const nextTrack = cloneTrack(track);
  const payload = storedEvent.event.payload;

  if (storedEvent.event.event_type === "run_started") {
    nextTrack.status = "running";
  }

  if (storedEvent.event.event_type === "position_solver_facts_recorded") {
    const solverFacts = payload.solver_facts as SolverFacts | undefined;
    if (solverFacts !== undefined) {
      nextTrack.solverFactsByPage.set(solverFacts.page_title, solverFacts);
      if (normalizeTitle(solverFacts.page_title) === normalizeTitle(nextTrack.currentPageTitle)) {
        nextTrack.currentDistance = solverFacts.shortest_path_length;
      }
      const moveIndex = Number(payload.move_index ?? 0);
      const move = nextTrack.moves.find((candidate) => candidate.moveIndex === moveIndex);
      if (move !== undefined) {
        move.distanceAfter = solverFacts.shortest_path_length;
      }
    }
  }

  if (storedEvent.event.event_type === "move_committed") {
    const moveIndex = Number(payload.move_index);
    const fromPageTitle = String(payload.from_page_title ?? "");
    const toPageTitle = String(payload.to_page_title ?? "");
    const fromFacts = nextTrack.solverFactsByPage.get(fromPageTitle);
    const toFacts = nextTrack.solverFactsByPage.get(toPageTitle);
    nextTrack.moves.push({
      moveIndex,
      fromPageTitle,
      toPageTitle,
      distanceBefore: fromFacts?.shortest_path_length,
      distanceAfter: toFacts?.shortest_path_length,
    });
    nextTrack.currentPageTitle = toPageTitle;
    nextTrack.currentDistance = toFacts?.shortest_path_length;
  }

  if (storedEvent.event.event_type === "run_terminated") {
    nextTrack.status = "completed";
    nextTrack.terminalOutcome = String(payload.terminal_outcome ?? "completed");
    nextTrack.terminationReason = stringValue(payload.termination_reason);
    nextTrack.totalStepAttempts = numberValue(payload.total_step_attempts);
    nextTrack.totalCommittedMoves = numberValue(payload.total_committed_moves);
    nextTrack.totalInvalidAttempts = numberValue(payload.total_invalid_attempts);
    nextTrack.estimatedCostUsd = numberValue(payload.estimated_cost_usd);
    nextTrack.totalModelTokens = numberValue(payload.total_model_tokens);
  }

  nextTracks.set(nextTrack.runId, nextTrack);
  return {
    ...state,
    tracksByRunId: nextTracks,
    latestStreamSequence: storedEvent.stream_sequence,
    eventLog: [...state.eventLog, storedEvent].slice(-80),
    viewingPageIndex: state.renderingMode === "live"
      ? Math.max(state.viewingPageIndex, maxMoveCount(nextTracks))
      : state.viewingPageIndex,
  };
}

export function setRaceViewingPageIndex(state: RaceViewState, viewingPageIndex: number): RaceViewState {
  return {
    ...state,
    renderingMode: "stepping",
    viewingPageIndex: Math.max(0, Math.min(viewingPageIndex, maxMoveCount(state.tracksByRunId))),
  };
}

export function enterRaceLiveMode(state: RaceViewState): RaceViewState {
  return {
    ...state,
    renderingMode: "live",
    viewingPageIndex: maxMoveCount(state.tracksByRunId),
  };
}

export function maxMoveCount(tracksByRunId: Map<string, ParticipantTrack>): number {
  return Math.max(0, ...[...tracksByRunId.values()].map((track) => track.moves.length));
}

function cloneTrack(track: ParticipantTrack): ParticipantTrack {
  return {
    ...track,
    moves: track.moves.map((move) => ({ ...move })),
    solverFactsByPage: new Map(track.solverFactsByPage),
  };
}

function normalizeTitle(title: string): string {
  return title.trim().replace(/_/g, " ").toLowerCase();
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}
