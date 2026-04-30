import "./styles.css";

import {
  ApiError,
  loadMeta,
  solvePath,
  type SolvePathMode,
  type SolveResponse,
} from "./lib/api";
import { attachTitleAutocomplete } from "./lib/autocomplete";
import { formatDurationMs, formatInteger } from "./lib/format";
import { renderPathGraph } from "./lib/path-graph";
import { WikipediaRandomService } from "./lib/random-pages";
import {
  buildSolverLinkUrl,
  readSolverLinkParams,
} from "./lib/solver-link";
import {
  getSolverResultTitle,
  getSolverResultView,
} from "./lib/solver-result-view";
import { createRandomTitleField } from "./lib/title-field";
import { WikipediaSearchService } from "./lib/wikipedia-search";

type SolveButtonMode = "solve" | "another" | "solving";

interface ArticlePair {
  startTitle: string;
  targetTitle: string;
}

function getRequiredElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLElement)) {
    throw new Error(`Missing required element: ${id}`);
  }
  return element as T;
}

function showFormError(formErrorElement: HTMLElement, message: string): void {
  formErrorElement.textContent = message;
  formErrorElement.classList.remove("hidden");
}

function hideFormError(formErrorElement: HTMLElement): void {
  formErrorElement.textContent = "";
  formErrorElement.classList.add("hidden");
}

function buildWikipediaUrl(title: string): string {
  return `https://en.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, "_"))}`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalizeTitle(title: string): string {
  return title.trim().toLowerCase();
}

function pairsMatch(left: ArticlePair | null, right: ArticlePair | null): boolean {
  if (left === null || right === null) {
    return false;
  }
  return (
    normalizeTitle(left.startTitle) === normalizeTitle(right.startTitle) &&
    normalizeTitle(left.targetTitle) === normalizeTitle(right.targetTitle)
  );
}

function renderSinglePathTimeline(resultsContainer: HTMLElement, path: string[]): void {
  const itemMarkup = path
    .map((title, titleIndex) => {
      const roleLabel = titleIndex === 0
        ? "Start"
        : titleIndex === path.length - 1
          ? "Target"
          : `Step ${titleIndex}`;
      return `
        <li class="timeline-item">
          <span class="timeline-index">${titleIndex}</span>
          <div class="timeline-copy">
            <span class="timeline-role">${roleLabel}</span>
            <a class="timeline-link" href="${buildWikipediaUrl(title)}" target="_blank" rel="noreferrer">${escapeHtml(title)}</a>
          </div>
        </li>
      `;
    })
    .join("");

  resultsContainer.innerHTML = `
    <div class="timeline-shell">
      <ol class="timeline-list">${itemMarkup}</ol>
    </div>
  `;
}

function renderSolveResponse(
  solveResponse: SolveResponse,
  pathMode: SolvePathMode,
  solverExperienceElement: HTMLElement,
  resultsPanelElement: HTMLElement,
  resultsTitleElement: HTMLElement,
  resultsContainer: HTMLElement,
  emptyStateElement: HTMLElement,
  summaryElement: HTMLElement,
): void {
  solverExperienceElement.classList.add("is-solved");
  resultsPanelElement.classList.add("is-visible");
  resultsTitleElement.textContent = getSolverResultTitle(pathMode);

  summaryElement.innerHTML = `
    <span class="summary-token">${solveResponse.paths.length} path${solveResponse.paths.length === 1 ? "" : "s"}</span>
    <span class="summary-token">${solveResponse.path_length === null ? "No route" : `${solveResponse.path_length} steps`}</span>
    <span class="summary-token">${formatInteger(solveResponse.pages_visited)} pages</span>
    <span class="summary-token">${formatInteger(solveResponse.links_scanned)} links</span>
    <span class="summary-token">${formatDurationMs(solveResponse.solve_ms)}</span>
  `;

  if (solveResponse.paths.length === 0 || solveResponse.path_length === null) {
    resultsContainer.classList.add("hidden");
    resultsContainer.innerHTML = "";
    emptyStateElement.classList.remove("hidden");
    emptyStateElement.innerHTML = `
      <strong>No path found.</strong>
      <span>The solver found both titles, but no path exists between them in ${escapeHtml(solveResponse.snapshot_id)}.</span>
    `;
    return;
  }

  emptyStateElement.classList.add("hidden");
  if (getSolverResultView(pathMode) === "timeline") {
    renderSinglePathTimeline(resultsContainer, solveResponse.paths[0] ?? []);
  } else {
    renderPathGraph(resultsContainer, solveResponse);
  }
  resultsContainer.classList.remove("hidden");
}

async function initializeHomePage(): Promise<void> {
  const solverExperienceElement = getRequiredElement<HTMLElement>("solver-experience");
  const startInput = getRequiredElement<HTMLInputElement>("start-title");
  const targetInput = getRequiredElement<HTMLInputElement>("target-title");
  const startSuggestions = getRequiredElement<HTMLElement>("start-suggestions");
  const targetSuggestions = getRequiredElement<HTMLElement>("target-suggestions");
  const startRandomButton = getRequiredElement<HTMLButtonElement>("start-random-button");
  const targetRandomButton = getRequiredElement<HTMLButtonElement>("target-random-button");
  const solveForm = getRequiredElement<HTMLFormElement>("solve-form");
  const solveButton = getRequiredElement<HTMLButtonElement>("solve-button");
  const swapButton = getRequiredElement<HTMLButtonElement>("swap-button");
  const pathModeSingleButton = getRequiredElement<HTMLButtonElement>("path-mode-single");
  const pathModeAllButton = getRequiredElement<HTMLButtonElement>("path-mode-all");
  const formErrorElement = getRequiredElement<HTMLElement>("form-error");
  const heroSnapshotElement = getRequiredElement<HTMLElement>("hero-snapshot");
  const heroNodeCountElement = getRequiredElement<HTMLElement>("hero-node-count");
  const heroEdgeCountElement = getRequiredElement<HTMLElement>("hero-edge-count");
  const resultsPanelElement = getRequiredElement<HTMLElement>("results-panel");
  const resultsTitleElement = getRequiredElement<HTMLElement>("results-title");
  const resultsContainer = getRequiredElement<HTMLElement>("results-container");
  const resultsEmptyState = getRequiredElement<HTMLElement>("results-empty-state");
  const resultSummary = getRequiredElement<HTMLElement>("result-summary");
  const startBoxElement = startInput.closest(".title-box");
  const targetBoxElement = targetInput.closest(".title-box");

  if (!(startBoxElement instanceof HTMLElement) || !(targetBoxElement instanceof HTMLElement)) {
    throw new Error("Title box containers are missing.");
  }

  const sharedRandomService = new WikipediaRandomService();
  const startFieldRandomService = new WikipediaRandomService();
  const targetFieldRandomService = new WikipediaRandomService();
  const titleResolutionService = new WikipediaSearchService();
  const pathModeButtons = [pathModeSingleButton, pathModeAllButton];
  const initialSolverLinkParams = readSolverLinkParams(window.location.search);

  let lastSolvedPair: ArticlePair | null = null;
  let lastSolvedPathMode: SolvePathMode | null = null;
  let selectedPathMode: SolvePathMode = "all_shortest";
  let solveButtonMode: SolveButtonMode = "solve";
  let isSolving = false;
  let supportedPathModes = new Set<SolvePathMode>(["single"]);

  function getCurrentExplicitPair(): ArticlePair | null {
    const startTitle = startInput.value.trim();
    const targetTitle = targetInput.value.trim();
    if (!startTitle || !targetTitle) {
      return null;
    }
    return {
      startTitle,
      targetTitle,
    };
  }

  function setSolveButtonMode(mode: SolveButtonMode): void {
    solveButtonMode = mode;
    if (mode === "solving") {
      solveButton.textContent = "Solving...";
      return;
    }
    if (mode === "another") {
      solveButton.textContent = "Another?";
      return;
    }
    solveButton.textContent = "Solve";
  }

  function syncPathModeButtons(): void {
    for (const buttonElement of pathModeButtons) {
      const buttonPathMode = buttonElement.dataset.pathMode as SolvePathMode;
      const isActive = buttonPathMode === selectedPathMode;
      const isSupported = supportedPathModes.has(buttonPathMode);
      buttonElement.classList.toggle("is-active", isActive);
      buttonElement.classList.toggle("is-disabled", !isSupported);
      buttonElement.setAttribute("aria-pressed", String(isActive));
      buttonElement.disabled = isSolving || !isSupported;
    }
  }

  function updateSolveButtonState(): void {
    if (isSolving) {
      syncPathModeButtons();
      return;
    }

    const currentPair = getCurrentExplicitPair();
    if (pairsMatch(currentPair, lastSolvedPair) && selectedPathMode === lastSolvedPathMode) {
      setSolveButtonMode("another");
      syncPathModeButtons();
      return;
    }
    setSolveButtonMode("solve");
    syncPathModeButtons();
  }

  async function resolveArticlePair(articlePair: ArticlePair): Promise<ArticlePair> {
    const [startResolution, targetResolution] = await Promise.all([
      titleResolutionService.resolveTitle(articlePair.startTitle),
      titleResolutionService.resolveTitle(articlePair.targetTitle),
    ]);

    return {
      startTitle: startResolution.canonicalTitle ?? articlePair.startTitle,
      targetTitle: targetResolution.canonicalTitle ?? articlePair.targetTitle,
    };
  }

  attachTitleAutocomplete({
    inputElement: startInput,
    suggestionListElement: startSuggestions,
  });
  attachTitleAutocomplete({
    inputElement: targetInput,
    suggestionListElement: targetSuggestions,
  });

  const startRandomController = createRandomTitleField({
    inputElement: startInput,
    buttonElement: startRandomButton,
    boxElement: startBoxElement,
    randomService: startFieldRandomService,
    onValueChange: updateSolveButtonState,
  });
  const targetRandomController = createRandomTitleField({
    inputElement: targetInput,
    buttonElement: targetRandomButton,
    boxElement: targetBoxElement,
    randomService: targetFieldRandomService,
    onValueChange: updateSolveButtonState,
  });

  swapButton.addEventListener("click", async () => {
    hideFormError(formErrorElement);
    const [startTitle, targetTitle] = await Promise.all([
      startRandomController.resolveTitle(),
      targetRandomController.resolveTitle(),
    ]);
    startRandomController.setValue(targetTitle);
    targetRandomController.setValue(startTitle);
  });

  for (const buttonElement of pathModeButtons) {
    buttonElement.addEventListener("click", async () => {
      const requestedPathMode = buttonElement.dataset.pathMode as SolvePathMode;
      if (isSolving || requestedPathMode === selectedPathMode || !supportedPathModes.has(requestedPathMode)) {
        return;
      }

      selectedPathMode = requestedPathMode;
      updateSolveButtonState();

      const currentPair = getCurrentExplicitPair();
      if (pairsMatch(currentPair, lastSolvedPair) && currentPair !== null) {
        await executeSolve(currentPair, requestedPathMode);
      }
    });
  }

  try {
    const meta = await loadMeta();
    heroSnapshotElement.textContent = meta.snapshot_id;
    heroNodeCountElement.textContent = `${formatInteger(meta.node_count)} pages`;
    heroEdgeCountElement.textContent = `${formatInteger(meta.edge_count)} links`;
    supportedPathModes = new Set(meta.supported_path_modes);
    if (supportedPathModes.has("all_shortest")) {
      selectedPathMode = "all_shortest";
    } else if (supportedPathModes.has(meta.default_path_mode)) {
      selectedPathMode = meta.default_path_mode;
    } else {
      selectedPathMode = supportedPathModes.values().next().value ?? "single";
    }
    const linkedPathMode = initialSolverLinkParams?.pathMode;
    if (
      linkedPathMode !== null &&
      linkedPathMode !== undefined &&
      supportedPathModes.has(linkedPathMode)
    ) {
      selectedPathMode = linkedPathMode;
    }
  } catch (error) {
    heroSnapshotElement.textContent = "Snapshot unavailable";
    heroNodeCountElement.textContent = "Graph unavailable";
    heroEdgeCountElement.textContent = "API unavailable";
  }

  updateSolveButtonState();

  function replaceSolverLinkUrl(articlePair: ArticlePair, pathMode: SolvePathMode): void {
    window.history.replaceState(
      window.history.state,
      "",
      buildSolverLinkUrl(window.location.href, articlePair, pathMode),
    );
  }

  async function executeSolve(articlePair: ArticlePair, pathMode: SolvePathMode): Promise<void> {
    isSolving = true;
    hideFormError(formErrorElement);
    solveButton.disabled = true;
    swapButton.disabled = true;
    setSolveButtonMode("solving");
    syncPathModeButtons();
    startRandomController.setDisabled(true);
    targetRandomController.setDisabled(true);
    resultSummary.innerHTML = '<span class="summary-token">Working...</span>';
    void sharedRandomService.refreshRandomTitlesInBackground();

    try {
      const resolvedArticlePair = await resolveArticlePair(articlePair);
      startRandomController.setValue(resolvedArticlePair.startTitle);
      targetRandomController.setValue(resolvedArticlePair.targetTitle);

      const solveResponse = await solvePath(
        resolvedArticlePair.startTitle,
        resolvedArticlePair.targetTitle,
        pathMode,
      );
      startRandomController.setValue(solveResponse.start_title);
      targetRandomController.setValue(solveResponse.target_title);
      lastSolvedPair = {
        startTitle: solveResponse.start_title,
        targetTitle: solveResponse.target_title,
      };
      lastSolvedPathMode = pathMode;
      replaceSolverLinkUrl(lastSolvedPair, pathMode);
      renderSolveResponse(
        solveResponse,
        pathMode,
        solverExperienceElement,
        resultsPanelElement,
        resultsTitleElement,
        resultsContainer,
        resultsEmptyState,
        resultSummary,
      );
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "The solver request failed.";
      showFormError(formErrorElement, message);
      resultSummary.innerHTML = '<span class="summary-token summary-token-error">Request failed</span>';
    } finally {
      isSolving = false;
      solveButton.disabled = false;
      swapButton.disabled = false;
      startRandomController.setDisabled(false);
      targetRandomController.setDisabled(false);
      updateSolveButtonState();
    }
  }

  if (initialSolverLinkParams !== null) {
    const linkedPair = {
      startTitle: initialSolverLinkParams.startTitle,
      targetTitle: initialSolverLinkParams.targetTitle,
    };
    startRandomController.setValue(linkedPair.startTitle);
    targetRandomController.setValue(linkedPair.targetTitle);
    void executeSolve(linkedPair, selectedPathMode);
  }

  solveForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (solveButtonMode === "another") {
      const currentPair = getCurrentExplicitPair();
      const excludedTitles = currentPair === null
        ? []
        : [currentPair.startTitle, currentPair.targetTitle];
      const [startTitle, targetTitle] = await sharedRandomService.getDistinctRandomTitles(
        2,
        excludedTitles,
      );
      const randomPair = {
        startTitle,
        targetTitle,
      };
      startRandomController.setValue(randomPair.startTitle);
      targetRandomController.setValue(randomPair.targetTitle);
      await executeSolve(randomPair, selectedPathMode);
      return;
    }

    const [startTitle, targetTitle] = await Promise.all([
      startRandomController.resolveTitle(),
      targetRandomController.resolveTitle(),
    ]);
    await executeSolve({
      startTitle,
      targetTitle,
    }, selectedPathMode);
  });
}

void initializeHomePage();
