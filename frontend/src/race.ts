import "./styles.css";

import { createRace, validateTitle, type RaceParticipantRequest } from "./lib/api";
import { attachTitleAutocomplete } from "./lib/autocomplete";
import { LoadingAnimation } from "./lib/loading-animation";
import { renderRaceGraph } from "./lib/race-graph";
import {
  createRaceViewState,
  enterRaceLiveMode,
  maxMoveCount,
  reduceStoredRaceEvent,
  setRaceViewingPageIndex,
} from "./lib/race-reducer";
import { connectRaceStream, loadRaceState } from "./lib/race-stream";
import type { ParticipantTrack, RaceStateResponse, RaceViewState, RunResultSummary, StoredRaceEvent } from "./lib/race-types";
import { WikipediaRandomService } from "./lib/random-pages";
import { createRandomTitleField } from "./lib/title-field";

function getElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLElement)) {
    throw new Error(`Missing element ${id}`);
  }
  return element as T;
}

const setupElement = getElement<HTMLElement>("race-setup");
const comingSoonElement = getElement<HTMLElement>("race-coming-soon");
const liveElement = getElement<HTMLElement>("race-live");
const formElement = getElement<HTMLFormElement>("race-form");
const startInput = getElement<HTMLInputElement>("race-start-title");
const targetInput = getElement<HTMLInputElement>("race-target-title");
const startSuggestions = getElement<HTMLElement>("race-start-suggestions");
const targetSuggestions = getElement<HTMLElement>("race-target-suggestions");
const startRandomButton = getElement<HTMLButtonElement>("race-start-random-button");
const targetRandomButton = getElement<HTMLButtonElement>("race-target-random-button");
const swapButton = getElement<HTMLButtonElement>("race-swap-button");
const startBox = getElement<HTMLElement>("race-start-box");
const targetBox = getElement<HTMLElement>("race-target-box");
const model1Select = getElement<HTMLSelectElement>("race-model-1");
const model2Select = getElement<HTMLSelectElement>("race-model-2");
const model1Card = model1Select.closest<HTMLElement>(".race-model-card");
const model2Card = model2Select.closest<HTMLElement>(".race-model-card");
const startButton = getElement<HTMLButtonElement>("race-start-button");
const modelErrorElement = getElement<HTMLElement>("race-model-error");
const formErrorElement = getElement<HTMLElement>("race-form-error");
const statusElement = getElement<HTMLElement>("race-status");
const raceResultHud = getElement<HTMLElement>("race-result-hud");
const raceResultHeader = getElement<HTMLButtonElement>("race-result-header");
const raceResultStartPage = getElement<HTMLElement>("race-result-start-page");
const raceResultTargetPage = getElement<HTMLElement>("race-result-target-page");
const liveButton = getElement<HTMLButtonElement>("race-live-button");
const graphElement = getElement<HTMLElement>("race-graph");
const progressElement = getElement<HTMLElement>("race-progress");
const playerDropdownsElement = getElement<HTMLElement>("player-dropdowns-container");
const player1Dropdown = getElement<HTMLElement>("player1-dropdown");
const player2Dropdown = getElement<HTMLElement>("player2-dropdown");
const scrubberElement = getElement<HTMLInputElement>("race-scrubber");
const raceResultsElement = getElement<HTMLElement>("race-results");
const loadingAnimation = new LoadingAnimation(getElement<HTMLElement>("race-loading"));
const randomService = new WikipediaRandomService();

let state: RaceViewState = createRaceViewState();
let socket: WebSocket | null = null;
let replayTimer: number | null = null;
let isSyncingPageLists = false;
let didAutoExpandResults = false;
let wasRaceFinished = false;

const PARTICIPANT_LOGOS: Record<string, string> = {
  claude_sonnet_4_6: "./assets/providers/anthropic.svg",
  claude_opus_4_6_max: "./assets/providers/anthropic.svg",
  gpt_5_5: "./assets/providers/openai.svg",
  gpt_5_4_xhigh: "./assets/providers/openai.svg",
};

const startValidation = createTitleValidationController({ inputElement: startInput, boxElement: startBox, role: "start" });
const targetValidation = createTitleValidationController({ inputElement: targetInput, boxElement: targetBox, role: "target" });

attachTitleAutocomplete({ inputElement: startInput, suggestionListElement: startSuggestions, onCommit: () => { void startValidation.validate(); } });
attachTitleAutocomplete({ inputElement: targetInput, suggestionListElement: targetSuggestions, onCommit: () => { void targetValidation.validate(); } });

const startField = createRandomTitleField({
  inputElement: startInput,
  buttonElement: startRandomButton,
  boxElement: startBox,
  randomService,
  onCommit: () => { void startValidation.validate(); },
});
const targetField = createRandomTitleField({
  inputElement: targetInput,
  buttonElement: targetRandomButton,
  boxElement: targetBox,
  randomService,
  onCommit: () => { void targetValidation.validate(); },
});

syncStartButtonState();

model1Select.addEventListener("change", () => {
  syncStartButtonState();
  if (!hasDuplicateParticipants()) {
    hideFormError();
  }
});
model2Select.addEventListener("change", () => {
  syncStartButtonState();
  if (!hasDuplicateParticipants()) {
    hideFormError();
  }
});

formElement.addEventListener("submit", (event) => {
  event.preventDefault();
  void startRace();
});

swapButton.addEventListener("click", () => {
  const startTitle = startInput.value;
  startField.setValue(targetInput.value);
  targetField.setValue(startTitle);
});

liveButton.addEventListener("click", () => {
  stopReplayPlayback();
  state = enterRaceLiveMode(state);
  render();
});

raceResultHeader.addEventListener("click", () => {
  raceResultHud.classList.toggle("expanded");
  if (raceHasFinished()) {
    didAutoExpandResults = true;
  }
});

document.querySelectorAll<HTMLButtonElement>("[data-dropdown-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    const dropdownId = button.dataset.dropdownToggle;
    if (dropdownId !== undefined) {
      const shouldExpand = !getElement<HTMLElement>(dropdownId).classList.contains("expanded");
      syncPlayerDropdownExpansion(shouldExpand);
    }
  });
});

scrubberElement.addEventListener("input", () => {
  stopReplayPlayback();
  state = setRaceViewingPageIndex(state, Number(scrubberElement.value));
  render();
});

void bootstrapFromUrl();

async function bootstrapFromUrl(): Promise<void> {
  const params = new URLSearchParams(window.location.search);
  const replayRaceId = params.get("replay");
  const liveRaceId = params.get("id");
  if (replayRaceId !== null && replayRaceId.trim() !== "") {
    await loadRaceReplay(
      replayRaceId,
      parseParticipantSelection(params.get("participants")),
    );
    return;
  }
  if (liveRaceId === null || liveRaceId.trim() === "") {
    return;
  }
  await loadAndConnectRace(liveRaceId);
}

async function startRace(): Promise<void> {
  hideFormError();
  if (hasDuplicateParticipants()) {
    showFormError("Choose two different participants for the race.");
    syncStartButtonState();
    return;
  }
  const [isStartValid, isTargetValid] = await Promise.all([
    startValidation.validate(),
    targetValidation.validate(),
  ]);
  if (!isStartValid || !isTargetValid) {
    syncFormError();
    syncStartButtonState();
    return;
  }
  try {
    loadingAnimation.start();
    const [startTitle, targetTitle] = await Promise.all([
      startField.resolveTitle(),
      targetField.resolveTitle(),
    ]);
    const response = await createRace({
      start_title: startTitle,
      target_title: targetTitle,
      participants: [parseModelSelection(model1Select.value, 1), parseModelSelection(model2Select.value, 2)],
      max_moves: 50,
    });
    window.history.replaceState({}, "", `./race.html?id=${encodeURIComponent(response.race_id)}`);
    await loadAndConnectRace(response.race_id);
  } catch (error) {
    loadingAnimation.hide();
    showFormError(error instanceof Error ? error.message : "Failed to create race.");
  }
}

function createTitleValidationController(options: {
  inputElement: HTMLInputElement;
  boxElement: HTMLElement;
  role: "start" | "target";
}): { canSubmit(): boolean; validate(): Promise<boolean>; errorMessage(): string | null } {
  const { inputElement, boxElement, role } = options;
  let validationTimer: number | null = null;
  let requestId = 0;
  let invalidTitle: string | null = null;
  let invalidSnapshotId: string | null = null;

  function setState(stateName: "empty" | "valid" | "invalid"): void {
    boxElement.classList.toggle("is-title-valid", stateName === "valid");
    boxElement.classList.toggle("is-title-invalid", stateName === "invalid");
    syncStartButtonState();
  }

  function clearValidation(): void {
    if (validationTimer !== null) {
      window.clearTimeout(validationTimer);
      validationTimer = null;
    }
    invalidTitle = null;
    invalidSnapshotId = null;
    setState("empty");
    syncFormError();
  }

  async function validate(): Promise<boolean> {
    if (validationTimer !== null) {
      window.clearTimeout(validationTimer);
      validationTimer = null;
    }
    const title = inputElement.value.trim();
    invalidTitle = null;
    invalidSnapshotId = null;
    if (title === "") {
      setState("empty");
      return true;
    }
    setState("empty");
    return runValidation(title);
  }

  async function runValidation(title: string): Promise<boolean> {
    const currentRequestId = ++requestId;
    try {
      const result = await validateTitle(title);
      if (currentRequestId !== requestId || inputElement.value.trim() !== title) {
        return true;
      }
      if (!result.exists || result.canonical_title === null) {
        invalidTitle = title;
        invalidSnapshotId = result.snapshot_id;
        setState("invalid");
        syncFormError();
        return false;
      }
      invalidTitle = null;
      invalidSnapshotId = null;
      inputElement.value = result.canonical_title;
      setState("valid");
      syncFormError();
      return true;
    } catch {
      if (currentRequestId === requestId) {
        invalidTitle = title;
        invalidSnapshotId = null;
        setState("invalid");
        syncFormError();
      }
      return false;
    }
  }

  inputElement.addEventListener("input", () => {
    clearValidation();
  });
  inputElement.addEventListener("blur", () => {
    void validate();
  });
  inputElement.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      void validate();
    }
  });

  return {
    canSubmit(): boolean {
      const title = inputElement.value.trim();
      return title === "" || invalidTitle === null || title !== invalidTitle;
    },
    validate,
    errorMessage(): string | null {
      const title = inputElement.value.trim();
      if (title === "" || invalidTitle === null || title !== invalidTitle) {
        return null;
      }
      return `${role === "start" ? "Start" : "Target"} page is not in ${invalidSnapshotId ?? "the loaded"} snapshot.`;
    },
  };
}

function syncStartButtonState(): void {
  const hasDuplicateModels = hasDuplicateParticipants();
  startButton.disabled = hasDuplicateModels || !startValidation?.canSubmit() || !targetValidation?.canSubmit();
  syncParticipantValidationState(hasDuplicateModels);
  syncModelError(hasDuplicateModels);
}

function hasDuplicateParticipants(): boolean {
  return model1Select.value === model2Select.value;
}

function syncParticipantValidationState(hasDuplicateModels: boolean): void {
  for (const card of [model1Card, model2Card]) {
    card?.classList.toggle("is-model-valid", !hasDuplicateModels);
    card?.classList.toggle("is-model-invalid", hasDuplicateModels);
  }
}

function syncModelError(hasDuplicateModels = hasDuplicateParticipants()): void {
  if (hasDuplicateModels) {
    modelErrorElement.textContent = "Choose two different participants.";
    modelErrorElement.classList.remove("hidden");
    return;
  }
  modelErrorElement.textContent = "";
  modelErrorElement.classList.add("hidden");
}

function syncFormError(): void {
  const message = startValidation.errorMessage() ?? targetValidation.errorMessage();
  if (message === null) {
    hideFormError();
    return;
  }
  showFormError(message);
}

async function loadAndConnectRace(raceId: string): Promise<void> {
  stopReplayPlayback();
  if (socket !== null) {
    socket.close();
  }
  const raceState = await loadRaceState(raceId);
  comingSoonElement.classList.add("hidden");
  setupElement.classList.add("hidden");
  liveElement.classList.remove("hidden");
  document.body.classList.add("race-active");
  state = createRaceViewState(raceState.metadata);
  didAutoExpandResults = raceState.metadata.status === "completed";
  wasRaceFinished = raceState.metadata.status === "completed";
  for (const event of raceState.events) {
    state = reduceStoredRaceEvent(state, event);
  }
  state = applyRunResults(state, raceState.run_results ?? []);
  render();
  if (raceState.metadata.status === "failed") {
    loadingAnimation.hide();
    statusElement.textContent = raceState.metadata.error_message ?? "failed";
  } else if (state.eventLog.length === 0) {
    loadingAnimation.start();
  } else {
    loadingAnimation.hide();
  }
  socket = connectRaceStream({
    raceId,
    afterSequence: state.latestStreamSequence,
    onEvent: handleStoredEvent,
    onStatus(status) {
      statusElement.textContent = status;
    },
  });
}

async function loadRaceReplay(raceId: string, participantIds: string[]): Promise<void> {
  stopReplayPlayback();
  if (socket !== null) {
    socket.close();
    socket = null;
  }
  const raceState = filterRaceStateParticipants(
    await loadRaceState(raceId),
    participantIds,
  );
  comingSoonElement.classList.add("hidden");
  setupElement.classList.add("hidden");
  liveElement.classList.remove("hidden");
  document.body.classList.add("race-active");
  state = createRaceViewState(raceState.metadata);
  didAutoExpandResults = false;
  wasRaceFinished = true;
  raceResultHud.classList.remove("expanded");
  for (const event of raceState.events) {
    state = reduceStoredRaceEvent(state, event);
  }
  state = applyRunResults(state, raceState.run_results ?? []);
  state = setRaceViewingPageIndex(state, 0);
  statusElement.textContent = "replay";
  liveButton.textContent = "Replay";
  loadingAnimation.hide();
  render();
  startReplayPlayback();
}

function filterRaceStateParticipants(raceState: RaceStateResponse, participantIds: string[]): RaceStateResponse {
  const selectedParticipants = participantIds.length === 0
    ? raceState.metadata.participants.slice(0, 2)
    : participantIds
      .map((participantId) => raceState.metadata.participants.find((participant) => participant.participant_id === participantId))
      .filter((participant) => participant !== undefined)
      .slice(0, 2);
  const selectedRunIds = new Set(selectedParticipants.map((participant) => participant.run_id));
  return {
    ...raceState,
    metadata: {
      ...raceState.metadata,
      participants: selectedParticipants,
    },
    events: raceState.events.filter((event) => selectedRunIds.has(event.event.run_id)),
    run_results: raceState.run_results?.filter((result) => selectedRunIds.has(result.run_id)),
  };
}

function parseParticipantSelection(value: string | null): string[] {
  if (value === null) {
    return [];
  }
  return value.split(",").map((participantId) => participantId.trim()).filter(Boolean);
}

function startReplayPlayback(): void {
  stopReplayPlayback();
  const stepReplay = () => {
    const maxPageIndex = maxMoveCount(state.tracksByRunId);
    if (state.viewingPageIndex >= maxPageIndex) {
      if (!didAutoExpandResults) {
        raceResultHud.classList.add("expanded");
        didAutoExpandResults = true;
      }
      stopReplayPlayback();
      return;
    }
    state = setRaceViewingPageIndex(state, state.viewingPageIndex + 1);
    render();
    replayTimer = window.setTimeout(stepReplay, 1100);
  };
  window.requestAnimationFrame(() => {
    replayTimer = window.setTimeout(stepReplay, 1100);
  });
}

function stopReplayPlayback(): void {
  if (replayTimer !== null) {
    window.clearTimeout(replayTimer);
    replayTimer = null;
  }
}

function applyRunResults(currentState: RaceViewState, runResults: RunResultSummary[]): RaceViewState {
  if (runResults.length === 0) {
    return currentState;
  }
  const nextTracks = new Map(currentState.tracksByRunId);
  for (const result of runResults) {
    const track = nextTracks.get(result.run_id);
    if (track === undefined) {
      continue;
    }
    nextTracks.set(result.run_id, {
      ...track,
      status: "completed",
      terminalOutcome: result.terminal_outcome,
      terminationReason: result.termination_reason,
      totalStepAttempts: result.total_step_attempts,
      totalCommittedMoves: result.total_committed_moves,
      totalInvalidAttempts: result.total_invalid_attempts,
      estimatedCostUsd: result.estimated_cost_usd,
      totalModelTokens: result.step_attempts?.reduce((total, attempt) => total + (attempt.model_metrics?.total_tokens ?? 0), 0),
      totalApiTimeMs: result.step_attempts?.reduce((total, attempt) => total + (attempt.model_metrics?.response_time_ms ?? 0), 0),
    });
  }
  return {
    ...currentState,
    tracksByRunId: nextTracks,
  };
}

function handleStoredEvent(storedEvent: StoredRaceEvent): void {
  state = reduceStoredRaceEvent(state, storedEvent);
  if (state.eventLog.length > 0) {
    loadingAnimation.hide();
  }
  render();
}

function render(): void {
  if (state.metadata !== null) {
    raceResultStartPage.textContent = state.metadata.start_title;
    raceResultTargetPage.textContent = state.metadata.target_title;
  }
  const maxPageIndex = maxMoveCount(state.tracksByRunId);
  scrubberElement.max = String(maxPageIndex);
  scrubberElement.value = String(state.renderingMode === "live" ? maxPageIndex : state.viewingPageIndex);
  updateScrubberThumbWidth(maxPageIndex);
  liveButton.classList.toggle("is-active", state.renderingMode === "live");
  renderProgressBars(maxPageIndex);
  renderRaceGraph(graphElement, state);
  renderPlayerDropdowns();
  renderRaceResults();
  const finished = raceHasFinished();
  if (finished && !wasRaceFinished && !didAutoExpandResults) {
    raceResultHud.classList.add("expanded");
    didAutoExpandResults = true;
  }
  wasRaceFinished = finished;
}

function renderProgressBars(maxPageIndex: number): void {
  progressElement.innerHTML = [...state.tracksByRunId.values()].map((track) => {
    const visibleDistance = visibleTrackDistance(track);
    const startDistance = state.metadata === null ? visibleDistance : track.solverFactsByPage.get(state.metadata.start_title)?.shortest_path_length ?? visibleDistance;
    const progressRatio = progressRatioForDistances(startDistance, visibleDistance);
    const progress = Math.max(-1, Math.min(1, progressRatio));
    const startPercent = 2;
    const fillLeft = progress < 0 ? progress * 100 : 0;
    const fillWidth = progress < 0 ? Math.max(2, Math.abs(progress) * 100) : startPercent + progress * (100 - startPercent);
    return `
      <div class="horizontal-progress-row" data-run-id="${escapeHtml(track.runId)}">
        <div class="horizontal-progress-label">
          <span class="race-track-dot" style="background:${track.color}"></span>
          <strong>${participantLabelMarkup(track)}</strong>
          <span>${escapeHtml(visibleTrackPage(track))}</span>
        </div>
        <div class="horizontal-progress-bar">
          <div class="horizontal-progress-fill ${progress < 0 ? "negative" : ""}" style="left:${fillLeft}%; width:${fillWidth}%; background:${progress < 0 ? "#d00000" : track.color}"></div>
        </div>
      </div>
    `;
  }).join("");
  progressElement.style.display = maxPageIndex === 0 && state.eventLog.length === 0 ? "none" : "flex";
}

function progressRatioForDistances(startDistance: number | null | undefined, visibleDistance: number | null | undefined): number {
  if (startDistance === null || startDistance === undefined || visibleDistance === null || visibleDistance === undefined || startDistance <= 0) {
    return 0;
  }
  if (visibleDistance < 0) {
    return 0;
  }
  if (visibleDistance > startDistance) {
    return (startDistance - visibleDistance) / startDistance;
  }
  if (visibleDistance === 0) {
    return 1;
  }
  if (startDistance === 1) {
    return 0;
  }
  return 0.95 * ((startDistance - visibleDistance) / (startDistance - 1));
}

function renderPlayerDropdowns(): void {
  const tracks = [...state.tracksByRunId.values()];
  playerDropdownsElement.style.display = tracks.length === 0 ? "none" : "flex";
  renderPlayerDropdown(player1Dropdown, tracks[0]);
  renderPlayerDropdown(player2Dropdown, tracks[1]);

  playerDropdownsElement.querySelectorAll<HTMLButtonElement>("button[data-index]").forEach((button) => {
    button.addEventListener("click", () => {
      state = setRaceViewingPageIndex(state, Number(button.dataset.index ?? 0));
      render();
    });
  });
  const lists = [...playerDropdownsElement.querySelectorAll<HTMLElement>(".player-dropdown-content")];
  lists.forEach((list) => {
    list.addEventListener("scroll", () => {
      if (isSyncingPageLists) {
        return;
      }
      isSyncingPageLists = true;
      for (const otherList of lists) {
        if (otherList !== list) {
          otherList.scrollTop = list.scrollTop;
        }
      }
      isSyncingPageLists = false;
    });
    if (state.renderingMode === "stepping") {
      window.requestAnimationFrame(() => {
        const currentItem = list.querySelector<HTMLElement>(".current");
        if (currentItem !== null) {
          list.scrollTop = currentItem.offsetTop + currentItem.offsetHeight - list.clientHeight;
        }
      });
    } else {
      list.querySelector(".current")?.scrollIntoView({ block: "nearest" });
    }
  });
}

function renderPlayerDropdown(dropdown: HTMLElement, track: ParticipantTrack | undefined): void {
  if (track === undefined) {
    dropdown.classList.add("hidden");
    return;
  }
  dropdown.classList.remove("hidden");
  const nameElement = dropdown.querySelector<HTMLElement>(".player-dropdown-name");
  const logoElement = dropdown.querySelector<HTMLElement>(".player-dropdown-logo");
  const statusElementForPlayer = dropdown.querySelector<HTMLElement>(".player-dropdown-status");
  const listElement = dropdown.querySelector<HTMLOListElement>(".player-dropdown-list");
  if (nameElement !== null) {
    nameElement.innerHTML = participantLabelMarkup(track);
  }
  if (logoElement !== null) {
    logoElement.style.background = track.color;
  }
  if (statusElementForPlayer !== null) {
    statusElementForPlayer.textContent = track.status;
    statusElementForPlayer.className = `player-dropdown-status ${track.status}`;
  }
  if (listElement !== null) {
    listElement.innerHTML = visiblePages(track).map((page, index) => `
      <li class="player-dropdown-item ${index === currentViewingIndex(track) ? "current" : ""}" data-index="${index}" style="border-right-color:${distanceChangeColor(index, track)}">
        <span class="player-dropdown-item-index">${index}</span>
        <button class="player-dropdown-item-title" type="button" data-index="${index}">${escapeHtml(page.title)}</button>
        <span class="player-dropdown-item-distance">${page.distance ?? "?"}</span>
      </li>
    `).join("");
  }
}

function syncPlayerDropdownExpansion(shouldExpand: boolean): void {
  [player1Dropdown, player2Dropdown].forEach((dropdown) => {
    dropdown.classList.toggle("expanded", shouldExpand);
  });
}

function renderRaceResults(): void {
  const tracks = [...state.tracksByRunId.values()];
  if (tracks.length === 0) {
    raceResultsElement.innerHTML = `<p class="race-results-empty">Race results will appear here.</p>`;
    return;
  }
  const outcomeByRunId = raceOutcomeByRunId(tracks);
  const scoreTracks = orderTracksForScore(tracks, outcomeByRunId);
  raceResultsElement.innerHTML = `
    ${renderRaceResultScore(tracks, outcomeByRunId)}
    <div class="race-results-grid">
      ${scoreTracks.map((track) => `
        <article class="race-result-card ${outcomeByRunId.get(track.runId) ?? "pending"}">
          <dl class="race-result-stats">
            <div><dt>cost</dt><dd>${formatCost(track.estimatedCostUsd)}</dd></div>
            <div><dt>tokens</dt><dd>${formatCompactNumber(track.totalModelTokens)}</dd></div>
            <div><dt>api time</dt><dd>${formatDuration(track.totalApiTimeMs)}</dd></div>
            <div><dt>invalid tool calls</dt><dd>${track.totalInvalidAttempts ?? 0}</dd></div>
          </dl>
        </article>
      `).join("")}
    </div>
  `;
}

function renderRaceResultScore(tracks: ParticipantTrack[], outcomeByRunId: Map<string, "win" | "loss" | "draw" | "pending">): string {
  if (tracks.length < 2) {
    return "";
  }
  const orderedTracks = orderTracksForScore(tracks, outcomeByRunId);
  const left = orderedTracks[0];
  const right = orderedTracks[1];
  const operator = outcomeByRunId.get(left.runId) === "draw" ? "=" : "<";
  return `
    <div class="race-result-score">
      <span class="race-result-score-name">${participantLabelMarkup(left)}</span>
      ${raceOutcomeBadge(outcomeByRunId.get(left.runId))}
      <span class="race-result-score-box">${escapeHtml(scoreLabel(left))} ${operator} ${escapeHtml(scoreLabel(right))}</span>
      ${raceOutcomeBadge(outcomeByRunId.get(right.runId))}
      <span class="race-result-score-name">${participantLabelMarkup(right)}</span>
    </div>
  `;
}

function orderTracksForScore(tracks: ParticipantTrack[], outcomeByRunId: Map<string, "win" | "loss" | "draw" | "pending">): ParticipantTrack[] {
  const winner = tracks.find((track) => outcomeByRunId.get(track.runId) === "win");
  if (winner === undefined) {
    return tracks.slice(0, 2);
  }
  const loser = tracks.find((track) => track.runId !== winner.runId) ?? tracks[1];
  return [winner, loser];
}

function raceOutcomeBadge(outcome: "win" | "loss" | "draw" | "pending" | undefined): string {
  const label = outcome === "win" ? "W" : outcome === "loss" ? "L" : outcome === "draw" ? "D" : "-";
  return `<span class="race-result-outcome outcome-${label.toLowerCase()}">${label}</span>`;
}

function scoreLabel(track: ParticipantTrack): string {
  return track.terminalOutcome === "success" ? String(track.totalCommittedMoves ?? track.moves.length) : "F";
}

function raceHasFinished(): boolean {
  const tracks = [...state.tracksByRunId.values()];
  return tracks.length > 0 && tracks.every((track) => track.status === "completed");
}

function participantLabelMarkup(track: ParticipantTrack): string {
  const logoPath = PARTICIPANT_LOGOS[track.participantId];
  const logo = logoPath === undefined ? "" : `<img class="race-provider-logo" src="${logoPath}" alt="" />`;
  return `<span class="race-participant-label">${logo}<span>${escapeHtml(track.displayName)}</span></span>`;
}

function raceOutcomeByRunId(tracks: ParticipantTrack[]): Map<string, "win" | "loss" | "draw" | "pending"> {
  const outcomes = new Map<string, "win" | "loss" | "draw" | "pending">();
  const completed = tracks.filter((track) => track.status === "completed");
  if (completed.length !== tracks.length) {
    tracks.forEach((track) => outcomes.set(track.runId, track.status === "completed" ? "draw" : "pending"));
    return outcomes;
  }
  const successful = tracks.filter((track) => track.terminalOutcome === "success");
  if (successful.length === 0) {
    tracks.forEach((track) => outcomes.set(track.runId, "draw"));
    return outcomes;
  }
  const bestMoves = Math.min(...successful.map((track) => track.totalCommittedMoves ?? track.moves.length));
  const winners = successful.filter((track) => (track.totalCommittedMoves ?? track.moves.length) === bestMoves);
  if (winners.length !== 1) {
    tracks.forEach((track) => outcomes.set(track.runId, successful.includes(track) ? "draw" : "loss"));
    return outcomes;
  }
  const winner = winners[0];
  tracks.forEach((track) => outcomes.set(track.runId, track.runId === winner.runId ? "win" : "loss"));
  return outcomes;
}

function formatCompactNumber(value: number | undefined): string {
  if (value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function formatCost(value: number | undefined): string {
  if (value === undefined) {
    return "-";
  }
  if (value === 0) {
    return "$0";
  }
  return `$${value.toFixed(value < 0.01 ? 4 : 2)}`;
}

function formatDuration(valueMs: number | undefined): string {
  if (valueMs === undefined) {
    return "-";
  }
  const totalSeconds = Math.round(valueMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function parseModelSelection(value: string, participantIndex: number): RaceParticipantRequest {
  const separator = value.includes("/") ? "/" : ":";
  const separatorIndex = value.indexOf(separator);
  const provider = separatorIndex === -1 ? "wikiarena" : value.slice(0, separatorIndex);
  const model = separatorIndex === -1 ? value : value.slice(separatorIndex + 1);
  const participantBaseId = `${provider}_${model}`.replace(/[^0-9A-Za-z_]+/g, "_").toLowerCase();
  return {
    participant_id: `${participantBaseId}_${participantIndex}`,
    display_name: displayNameForParticipant(provider, model),
    provider,
    model,
  };
}

function displayNameForParticipant(provider: string, model: string): string {
  if (provider === "wikiarena" && model === "random") {
    return "Random Walker";
  }
  if (provider === "wikiarena" && model === "first") {
    return "First Link";
  }
  return model;
}

function visiblePages(track: ParticipantTrack): Array<{ title: string; distance?: number | null }> {
  const pages = [{ title: state.metadata?.start_title ?? track.currentPageTitle, distance: state.metadata === null ? undefined : track.solverFactsByPage.get(state.metadata.start_title)?.shortest_path_length }];
  const maxIndex = state.renderingMode === "live" ? Number.POSITIVE_INFINITY : state.viewingPageIndex;
  for (const move of track.moves.filter((candidate) => candidate.moveIndex <= maxIndex)) {
    pages.push({ title: move.toPageTitle, distance: move.distanceAfter });
  }
  return pages;
}

function currentViewingIndex(track: ParticipantTrack): number {
  return Math.min(visiblePages(track).length - 1, state.renderingMode === "live" ? track.moves.length : state.viewingPageIndex);
}

function visibleTrackPage(track: ParticipantTrack): string {
  const pages = visiblePages(track);
  return pages[Math.max(0, pages.length - 1)]?.title ?? track.currentPageTitle;
}

function visibleTrackDistance(track: ParticipantTrack): number | null | undefined {
  const pages = visiblePages(track);
  for (let index = pages.length - 1; index >= 0; index -= 1) {
    const distance = pages[index]?.distance;
    if (distance !== undefined && distance !== null) {
      return distance;
    }
  }
  return undefined;
}

function distanceChangeColor(pageIndex: number, track: ParticipantTrack): string {
  if (pageIndex === 0) {
    return "#d7d7d7";
  }
  const move = track.moves[pageIndex - 1];
  if (move === undefined || move.distanceBefore === undefined || move.distanceAfter === undefined || move.distanceBefore === null || move.distanceAfter === null) {
    return "#d7d7d7";
  }
  const distanceChange = move.distanceBefore - move.distanceAfter;
  if (distanceChange > 0) {
    return "#00843d";
  }
  if (distanceChange === 0) {
    return "#ffb000";
  }
  return "#d00000";
}

function updateScrubberThumbWidth(maxPageIndex: number): void {
  const totalPositions = maxPageIndex + 1;
  const handleWidthPercent = Math.max(5, 100 / totalPositions);
  const containerWidth = scrubberElement.parentElement?.offsetWidth ?? 0;
  const handleWidthPx = containerWidth > 0
    ? Math.max(20, (containerWidth * handleWidthPercent) / 100)
    : Math.max(20, handleWidthPercent);
  scrubberElement.style.setProperty("--thumb-width", `${handleWidthPx}px`);
}

function showFormError(message: string): void {
  formErrorElement.textContent = message;
  formErrorElement.classList.remove("hidden");
}

function hideFormError(): void {
  formErrorElement.textContent = "";
  formErrorElement.classList.add("hidden");
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
