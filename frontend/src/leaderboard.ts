import "./styles.css";

interface LeaderboardParticipant {
  participantId: string;
  displayName: string;
  runs: number;
  rankingEligibleRuns: number;
  successes: number;
  pairwiseWins: number;
  pairwiseLosses: number;
  pairwiseDraws: number;
  pairwiseSkipped: number;
  totalEstimatedCostUsd: number | null;
  estimatedCostUsdPerSuccess: number | null;
  totalStepAttempts: number;
  totalInvalidAttempts: number;
  stepErrorRate: number | null;
  totalModelResponseTimeMs: number | null;
  elo: number | null;
}

interface LeaderboardData {
  benchmarkId: string;
  snapshotId: string;
  sourcePath: string;
  artifactDir: string;
  generatedFromRuns: number;
  rankedFromRuns: number;
  totalRaces: number;
  excludedParticipants: string[];
  scoringPolicy: {
    tieBreaker: string;
    unsolvedPairPolicy: string;
  };
  pairwiseComparisons: number;
  pairwiseSkippedComparisons: number;
  participants: LeaderboardParticipant[];
}

interface ReplayParticipant {
  participantId: string;
  displayName: string;
  runId: string;
  terminalOutcome: string;
  committedMoves: number;
  scoreMoves: number;
  scoreLabel: string;
  invalidAttempts: number;
  estimatedCostUsd: number;
  elo: number | null;
}

interface ReplayRace {
  raceId: string;
  taskId: string;
  startTitle: string;
  targetTitle: string;
  optimalMoves: number | null;
  winnerParticipantId: string | null;
  victoryMarginMoves: number | null;
  participants: ReplayParticipant[];
}

interface ReplayManifest {
  generatedFromRuns: number;
  rankedFromRuns: number;
  excludedParticipants: string[];
  scoringPolicy: {
    tieBreaker: string;
    unsolvedPairPolicy: string;
  };
  totalRaces: number;
  races: ReplayRace[];
}

const MAX_VISIBLE_RACES = 60;
const MAX_SECTION_RACES = 30;

const PARTICIPANT_LOGOS: Record<string, string> = {
  claude_sonnet_4_6: "./assets/providers/anthropic.svg",
  claude_opus_4_6_max: "./assets/providers/anthropic.svg",
  gpt_5_5: "./assets/providers/openai.svg",
  gpt_5_4_xhigh: "./assets/providers/openai.svg",
};

function getRequiredElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLElement)) {
    throw new Error(`Missing required element: ${id}`);
  }
  return element as T;
}

function formatPercent(numerator: number, denominator: number): string {
  if (denominator <= 0) {
    return "--";
  }
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

function formatRate(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "--";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatDuration(valueMs: number | null): string {
  if (valueMs === null || !Number.isFinite(valueMs)) {
    return "--";
  }
  const totalSeconds = Math.round(valueMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) {
    return `${minutes}m ${seconds}s`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderLeaderboard(data: LeaderboardData): void {
  const rows = getRequiredElement("leaderboard-rows");
  const sourceNote = getRequiredElement("leaderboard-source-note");
  sourceNote.textContent = "";

  rows.innerHTML = data.participants
    .map((participant, index) => {
      const successRate = formatPercent(
        participant.successes,
        participant.rankingEligibleRuns,
      );
      return `
        <div class="leaderboard-row" role="row">
          <span role="cell">${index + 1}</span>
          <span role="cell" class="leaderboard-model-cell">
            ${renderLeaderboardLogo(participant)}
            <strong>${escapeHtml(participant.displayName)}</strong>
          </span>
          <span role="cell">${participant.elo ?? "--"}</span>
          <span role="cell">${successRate}</span>
          <span role="cell">${formatRate(participant.stepErrorRate)}</span>
          <span role="cell">${formatDuration(participant.totalModelResponseTimeMs)}</span>
        </div>
      `;
    })
    .join("");
}

function renderLeaderboardLogo(participant: LeaderboardParticipant): string {
  const logoPath = PARTICIPANT_LOGOS[participant.participantId];
  if (logoPath === undefined) {
    return "";
  }
  return `<img class="leaderboard-provider-logo" src="${logoPath}" alt="" />`;
}

function renderRaceBrowser(manifest: ReplayManifest, query: string): void {
  const sectionsElement = getRequiredElement("race-browser-sections");
  const note = getRequiredElement("race-browser-note");
  const normalizedQuery = query.trim().toLowerCase();
  const matchingRaces = manifest.races.filter((race) => {
    if (normalizedQuery === "") {
      return true;
    }
    return `${race.startTitle} ${race.targetTitle} ${race.taskId}`.toLowerCase().includes(normalizedQuery);
  });
  note.classList.toggle("hidden", normalizedQuery === "");
  note.textContent = `${matchingRaces.length} matching benchmark races${matchingRaces.length > MAX_VISIBLE_RACES ? `, showing first ${MAX_VISIBLE_RACES}` : ""}.`;
  if (normalizedQuery !== "") {
    sectionsElement.innerHTML = renderRaceSection({
      title: "Search results",
      metricLabel: "by task length",
      races: matchingRaces.slice(0, MAX_VISIBLE_RACES),
      metric: taskLengthMetric,
    });
    return;
  }
  sectionsElement.innerHTML = [
    renderRaceSection({ title: "Longest solved tasks", metricLabel: "by task length descending", races: longestSolvedTasks(manifest.races), metric: taskLengthMetric }),
    renderRaceSection({ title: "Shortest failed tasks", metricLabel: "by task length ascending", races: shortestFailedTasks(manifest.races), metric: taskLengthMetric }),
    renderRaceSection({ title: "Perfect Races", metricLabel: "by task length descending", races: perfectPlay(manifest.races), metric: taskLengthMetric }),
    renderRaceSection({ title: "Sole solves", metricLabel: "by winning moves ascending", races: soleSolves(manifest.races), metric: winnerMovesMetric }),
    renderRaceSection({ title: "Upsets", metricLabel: "by margin descending", races: upsets(manifest.races), metric: marginMetric }),
    renderRaceSection({ title: "Blowouts", metricLabel: "by margin descending", races: blowouts(manifest.races), metric: marginMetric }),
  ].join("");
}

function renderRaceSection(options: {
  title: string;
  metricLabel: string;
  races: ReplayRace[];
  metric: (race: ReplayRace) => string;
}): string {
  const { title, metricLabel, races, metric } = options;
  const rows = races.length === 0
    ? `<p class="note-copy race-browser-empty">No races in this category yet.</p>`
    : races.map((race) => renderRaceCard(race, metric)).join("");
  return `
    <section class="race-browser-section">
      <div class="race-browser-section-header">
        <h3>${escapeHtml(title)}</h3>
        <span>${escapeHtml(metricLabel)}</span>
      </div>
      <div class="race-browser-list">${rows}</div>
    </section>
  `;
}

function renderRaceCard(race: ReplayRace, metric: (race: ReplayRace) => string): string {
  const selectedParticipants = displayParticipantsForRace(race);
  const replayUrl = `./race.html?replay=${encodeURIComponent(race.raceId)}&participants=${encodeURIComponent(selectedParticipants.map((participant) => participant.participantId).join(","))}`;
  const [left, right] = orderedScoreParticipants(race, selectedParticipants);
  const scoreOperator = race.winnerParticipantId === null ? "=" : "<";
  return `
    <article class="race-browser-card">
      <div class="race-browser-metric">${escapeHtml(metric(race))}</div>
      <div class="race-browser-game">
        <div class="race-browser-score">
          ${renderScoreParticipantName(left, "left")}
          <span class="race-browser-versus">vs.</span>
          ${renderOutcomeBadge(race, left, "left")}
          <span class="race-browser-score-box">${escapeHtml(left?.scoreLabel ?? "--")} ${scoreOperator} ${escapeHtml(right?.scoreLabel ?? "--")}</span>
          ${renderOutcomeBadge(race, right, "right")}
          ${renderScoreParticipantName(right, "right")}
        </div>
        <div class="race-browser-task" title="${escapeHtml(race.startTitle)} -> ${escapeHtml(race.targetTitle)}">
          <span>${escapeHtml(race.startTitle)}</span>
          <span>-&gt;</span>
          <span>${escapeHtml(race.targetTitle)}</span>
        </div>
      </div>
      <a class="path-mode-button cta-link race-browser-replay" href="${replayUrl}">Watch</a>
    </article>
  `;
}

function displayParticipantsForRace(race: ReplayRace): ReplayParticipant[] {
  const [left, right] = orderedScoreParticipants(race, race.participants);
  return [left, right].filter(
    (participant): participant is ReplayParticipant => participant !== undefined,
  );
}

function taskLengthMetric(race: ReplayRace): string {
  return race.optimalMoves === null ? "--" : String(race.optimalMoves);
}

function marginMetric(race: ReplayRace): string {
  return race.victoryMarginMoves === null ? "--" : String(race.victoryMarginMoves);
}

function winnerMovesMetric(race: ReplayRace): string {
  const winner = race.participants.find((participant) => participant.participantId === race.winnerParticipantId);
  return winner === undefined ? "--" : winner.scoreLabel;
}

function renderScoreParticipantName(participant: ReplayParticipant | undefined, side: "left" | "right"): string {
  if (participant === undefined) {
    return "";
  }
  return `
    <span class="race-browser-participant participant-${side}">
      ${renderParticipantLogo(participant)}
      <strong>${escapeHtml(participant.displayName)}</strong>
    </span>
  `;
}

function renderParticipantLogo(participant: ReplayParticipant): string {
  const logoPath = PARTICIPANT_LOGOS[participant.participantId];
  if (logoPath === undefined) {
    return "";
  }
  return `<img class="race-browser-provider-logo" src="${logoPath}" alt="" />`;
}

function renderOutcomeBadge(race: ReplayRace, participant: ReplayParticipant | undefined, side: "left" | "right"): string {
  if (participant === undefined) {
    return "";
  }
  const outcome = scoreOutcome(race, participant);
  return `<span class="race-browser-outcome outcome-${outcome.toLowerCase()} outcome-${side}">${outcome}</span>`;
}

function scoreOutcome(race: ReplayRace, participant: ReplayParticipant): "W" | "L" | "D" {
  if (race.winnerParticipantId === null) {
    return "D";
  }
  return race.winnerParticipantId === participant.participantId ? "W" : "L";
}

function orderedScoreParticipants(race: ReplayRace, participants: ReplayParticipant[]): [ReplayParticipant | undefined, ReplayParticipant | undefined] {
  const sortedParticipants = [...participants].sort(
    (left, right) => left.scoreMoves - right.scoreMoves || left.displayName.localeCompare(right.displayName),
  );
  if (race.winnerParticipantId === null) {
    return [sortedParticipants[0], sortedParticipants[1]];
  }
  const winner = participants.find((participant) => participant.participantId === race.winnerParticipantId);
  const loser = sortedParticipants.find((participant) => participant.participantId !== race.winnerParticipantId);
  return [winner, loser];
}

function longestSolvedTasks(races: ReplayRace[]): ReplayRace[] {
  return races
    .filter((race) => race.optimalMoves !== null && race.participants.some((participant) => participant.terminalOutcome === "success"))
    .sort((left, right) => (right.optimalMoves ?? 0) - (left.optimalMoves ?? 0))
    .slice(0, MAX_SECTION_RACES);
}

function shortestFailedTasks(races: ReplayRace[]): ReplayRace[] {
  return races
    .filter((race) => race.optimalMoves !== null && race.participants.every((participant) => participant.terminalOutcome !== "success"))
    .sort((left, right) => (left.optimalMoves ?? 0) - (right.optimalMoves ?? 0))
    .slice(0, MAX_SECTION_RACES);
}

function upsets(races: ReplayRace[]): ReplayRace[] {
  return races
    .filter((race) => {
      const [winner, loser] = orderedScoreParticipants(race, race.participants);
      return winner !== undefined
        && loser !== undefined
        && winner.terminalOutcome === "success"
        && loser.terminalOutcome === "success"
        && winner.elo !== null
        && loser.elo !== null
        && winner.elo < loser.elo;
    })
    .sort((left, right) => upsetScore(right) - upsetScore(left) || (right.victoryMarginMoves ?? 0) - (left.victoryMarginMoves ?? 0))
    .slice(0, MAX_SECTION_RACES);
}

function upsetScore(race: ReplayRace): number {
  const [winner, loser] = orderedScoreParticipants(race, race.participants);
  if (winner === undefined || loser === undefined || winner.elo === null || loser.elo === null) {
    return 0;
  }
  return loser.elo - winner.elo;
}

function blowouts(races: ReplayRace[]): ReplayRace[] {
  return races
    .filter((race) => race.victoryMarginMoves !== null && race.participants.every((participant) => participant.terminalOutcome === "success"))
    .sort((left, right) => (right.victoryMarginMoves ?? 0) - (left.victoryMarginMoves ?? 0))
    .slice(0, MAX_SECTION_RACES);
}

function soleSolves(races: ReplayRace[]): ReplayRace[] {
  return races
    .filter((race) => race.participants.filter((participant) => participant.terminalOutcome === "success").length === 1)
    .sort((left, right) => winnerScoreMoves(left) - winnerScoreMoves(right))
    .slice(0, MAX_SECTION_RACES);
}

function winnerScoreMoves(race: ReplayRace): number {
  const winner = race.participants.find((participant) => participant.participantId === race.winnerParticipantId);
  return winner?.scoreMoves ?? Number.POSITIVE_INFINITY;
}

function perfectPlay(races: ReplayRace[]): ReplayRace[] {
  return races
    .filter((race) => race.optimalMoves !== null && race.participants.some((participant) => participant.terminalOutcome === "success" && participant.committedMoves === race.optimalMoves))
    .sort((left, right) => (right.optimalMoves ?? 0) - (left.optimalMoves ?? 0))
    .slice(0, MAX_SECTION_RACES);
}

async function initializeLeaderboard(): Promise<void> {
  const [leaderboardResponse, replayResponse] = await Promise.all([
    fetch("/data/leaderboard.json"),
    fetch("/data/benchmark-races.json"),
  ]);
  if (!leaderboardResponse.ok) {
    throw new Error(`Failed to load leaderboard data: ${leaderboardResponse.status}`);
  }
  if (!replayResponse.ok) {
    throw new Error(`Failed to load replay manifest: ${replayResponse.status}`);
  }
  renderLeaderboard(await leaderboardResponse.json() as LeaderboardData);
  const replayManifest = await replayResponse.json() as ReplayManifest;
  renderRaceBrowser(replayManifest, "");
  const searchInput = getRequiredElement<HTMLInputElement>("race-browser-search");
  searchInput.addEventListener("input", () => {
    renderRaceBrowser(replayManifest, searchInput.value);
  });
}

initializeLeaderboard().catch((error: unknown) => {
  const sourceNote = getRequiredElement("leaderboard-source-note");
  sourceNote.textContent = error instanceof Error
    ? error.message
    : "Failed to load leaderboard data.";
});
