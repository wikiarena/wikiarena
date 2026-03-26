import "./styles.css";

import { ApiError, loadMeta, solvePath, type SolveResponse } from "./lib/api";
import { attachTitleAutocomplete } from "./lib/autocomplete";
import { formatDurationMs, formatInteger } from "./lib/format";
import { WikipediaRandomService } from "./lib/random-pages";

type SolveButtonMode = "solve" | "another" | "solving";

interface ArticlePair {
  startTitle: string;
  targetTitle: string;
}

interface RandomFieldController {
  setDisabled(disabled: boolean): void;
  setValue(title: string): void;
  resolveTitle(): Promise<string>;
}

function getRequiredElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLElement)) {
    throw new Error(`Missing required element: ${id}`);
  }
  return element as T;
}

function setStatus(
  element: HTMLElement,
  label: string,
  state: "loading" | "ready" | "error",
): void {
  element.textContent = label;
  element.classList.remove("is-loading", "is-ready", "is-error");
  if (state === "loading") {
    element.classList.add("is-loading");
  }
  if (state === "ready") {
    element.classList.add("is-ready");
  }
  if (state === "error") {
    element.classList.add("is-error");
  }
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

function formatServiceVersion(version: string): string {
  return version.startsWith("v") ? version : `v${version}`;
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

function createRandomFieldController(options: {
  inputElement: HTMLInputElement;
  buttonElement: HTMLButtonElement;
  boxElement: HTMLElement;
  randomService: WikipediaRandomService;
  onValueChange: () => void;
}): RandomFieldController {
  const {
    inputElement,
    buttonElement,
    boxElement,
    randomService,
    onValueChange,
  } = options;

  const defaultPlaceholder = inputElement.placeholder;

  let cyclingCallback: ((title: string) => void) | null = null;
  let isRandomizing = false;
  let currentDisplayedTitle = "";

  function commitTitle(title: string): string {
    const resolvedTitle = title.trim();
    if (!resolvedTitle) {
      return "";
    }

    inputElement.value = resolvedTitle;
    inputElement.placeholder = defaultPlaceholder;
    currentDisplayedTitle = resolvedTitle;
    stopCycling();
    onValueChange();
    return resolvedTitle;
  }

  function startCycling(): void {
    if (cyclingCallback !== null || isRandomizing || inputElement.value.trim() !== "") {
      return;
    }

    cyclingCallback = (title: string) => {
      if (isRandomizing || document.activeElement === inputElement || inputElement.value.trim() !== "") {
        return;
      }
      currentDisplayedTitle = title;
      inputElement.placeholder = title;
    };
    randomService.registerCyclingCallback(cyclingCallback);
  }

  function stopCycling(): void {
    if (cyclingCallback !== null) {
      randomService.unregisterCyclingCallback(cyclingCallback);
      cyclingCallback = null;
    }

    if (!isRandomizing) {
      inputElement.placeholder = defaultPlaceholder;
    }
  }

  async function randomizeTitle(): Promise<void> {
    if (isRandomizing || buttonElement.disabled) {
      return;
    }

    isRandomizing = true;
    stopCycling();
    boxElement.classList.add("is-randomizing");
    buttonElement.disabled = true;
    inputElement.value = "";
    onValueChange();

    try {
      const finalTitle = await randomService.startSlotMachine((title, spinning) => {
        currentDisplayedTitle = title;
        if (spinning) {
          inputElement.placeholder = title;
          return;
        }

        commitTitle(title);
      });
      commitTitle(finalTitle);
    } finally {
      isRandomizing = false;
      boxElement.classList.remove("is-randomizing");
      buttonElement.disabled = false;
      if (inputElement.value.trim() === "") {
        startCycling();
      }
    }
  }

  inputElement.addEventListener("focus", () => {
    stopCycling();
  });

  inputElement.addEventListener("blur", () => {
    window.setTimeout(() => {
      if (inputElement.value.trim() === "" && !isRandomizing) {
        startCycling();
      }
    }, 80);
  });

  inputElement.addEventListener("input", () => {
    currentDisplayedTitle = inputElement.value.trim() || currentDisplayedTitle;
    if (inputElement.value.trim() === "") {
      startCycling();
    } else {
      stopCycling();
    }
    onValueChange();
  });

  buttonElement.addEventListener("click", () => {
    void randomizeTitle();
  });

  startCycling();

  return {
    setDisabled(disabled: boolean): void {
      buttonElement.disabled = disabled;
      if (disabled) {
        stopCycling();
        return;
      }
      if (inputElement.value.trim() === "" && !isRandomizing) {
        startCycling();
      }
    },
    setValue(title: string): void {
      commitTitle(title);
    },
    async resolveTitle(): Promise<string> {
      const typedTitle = inputElement.value.trim();
      if (typedTitle) {
        currentDisplayedTitle = typedTitle;
        return typedTitle;
      }

      if (currentDisplayedTitle.trim()) {
        return commitTitle(currentDisplayedTitle);
      }

      const randomTitle = await randomService.getRandomTitle();
      return commitTitle(randomTitle);
    },
  };
}

function renderPathCards(resultsContainer: HTMLElement, solveResponse: SolveResponse): void {
  resultsContainer.innerHTML = solveResponse.paths
    .map((path, pathIndex) => {
      const itemsMarkup = path
        .map(
          (title, titleIndex) => `
            <li class="path-item">
              <span class="path-index">${titleIndex}</span>
              <div class="path-copy">
                <span class="path-role">${
                  titleIndex === 0
                    ? "Start"
                    : titleIndex === path.length - 1
                      ? "Target"
                      : `Step ${titleIndex}`
                }</span>
                <a class="path-link" href="${buildWikipediaUrl(title)}" target="_blank" rel="noreferrer">${escapeHtml(title)}</a>
              </div>
            </li>
          `,
        )
        .join("");

      return `
        <article class="path-sheet" style="--path-delay: ${pathIndex};">
          <header class="path-sheet-header">
            <span class="path-sheet-label">Path ${pathIndex + 1}</span>
            <span class="path-sheet-stat">${solveResponse.path_length ?? 0} steps</span>
          </header>
          <ol class="path-list">${itemsMarkup}</ol>
        </article>
      `;
    })
    .join("");
}

function renderSolveResponse(
  solveResponse: SolveResponse,
  solverExperienceElement: HTMLElement,
  resultsPanelElement: HTMLElement,
  resultsContainer: HTMLElement,
  emptyStateElement: HTMLElement,
  summaryElement: HTMLElement,
): void {
  solverExperienceElement.classList.add("is-solved");
  resultsPanelElement.classList.add("is-visible");

  summaryElement.innerHTML = `
    <span class="summary-token">${formatDurationMs(solveResponse.solve_ms)}</span>
    <span class="summary-token">${solveResponse.paths.length} path${solveResponse.paths.length === 1 ? "" : "s"}</span>
    <span class="summary-token">${solveResponse.path_length === null ? "No route" : `${solveResponse.path_length} steps`}</span>
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
  renderPathCards(resultsContainer, solveResponse);
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
  const formErrorElement = getRequiredElement<HTMLElement>("form-error");
  const statusElement = getRequiredElement<HTMLElement>("solver-status");
  const heroSnapshotElement = getRequiredElement<HTMLElement>("hero-snapshot");
  const heroNodeCountElement = getRequiredElement<HTMLElement>("hero-node-count");
  const heroEdgeCountElement = getRequiredElement<HTMLElement>("hero-edge-count");
  const resultsPanelElement = getRequiredElement<HTMLElement>("results-panel");
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

  let lastSolvedPair: ArticlePair | null = null;
  let solveButtonMode: SolveButtonMode = "solve";
  let isSolving = false;

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

  function updateSolveButtonState(): void {
    if (isSolving) {
      return;
    }

    const currentPair = getCurrentExplicitPair();
    if (pairsMatch(currentPair, lastSolvedPair)) {
      setSolveButtonMode("another");
      return;
    }
    setSolveButtonMode("solve");
  }

  attachTitleAutocomplete({
    inputElement: startInput,
    suggestionListElement: startSuggestions,
  });
  attachTitleAutocomplete({
    inputElement: targetInput,
    suggestionListElement: targetSuggestions,
  });

  const startRandomController = createRandomFieldController({
    inputElement: startInput,
    buttonElement: startRandomButton,
    boxElement: startBoxElement,
    randomService: startFieldRandomService,
    onValueChange: updateSolveButtonState,
  });
  const targetRandomController = createRandomFieldController({
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

  setStatus(statusElement, "Connecting", "loading");

  try {
    const meta = await loadMeta();
    heroSnapshotElement.textContent = meta.snapshot_id;
    heroNodeCountElement.textContent = `${formatInteger(meta.node_count)} pages`;
    heroEdgeCountElement.textContent = `${formatInteger(meta.edge_count)} links`;
    setStatus(statusElement, formatServiceVersion(meta.service_version), "ready");
  } catch (error) {
    heroSnapshotElement.textContent = "Snapshot unavailable";
    heroNodeCountElement.textContent = "Graph unavailable";
    heroEdgeCountElement.textContent = "API unavailable";
    const message = error instanceof ApiError ? error.message : "Metadata unavailable";
    setStatus(statusElement, message, "error");
  }

  async function executeSolve(articlePair: ArticlePair): Promise<void> {
    isSolving = true;
    hideFormError(formErrorElement);
    solveButton.disabled = true;
    swapButton.disabled = true;
    setSolveButtonMode("solving");
    startRandomController.setDisabled(true);
    targetRandomController.setDisabled(true);
    resultSummary.innerHTML = '<span class="summary-token">Working...</span>';
    void sharedRandomService.refreshRandomTitlesInBackground();

    try {
      const solveResponse = await solvePath(
        articlePair.startTitle,
        articlePair.targetTitle,
      );
      startRandomController.setValue(solveResponse.start_title);
      targetRandomController.setValue(solveResponse.target_title);
      lastSolvedPair = {
        startTitle: solveResponse.start_title,
        targetTitle: solveResponse.target_title,
      };
      renderSolveResponse(
        solveResponse,
        solverExperienceElement,
        resultsPanelElement,
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
      await executeSolve(randomPair);
      return;
    }

    const [startTitle, targetTitle] = await Promise.all([
      startRandomController.resolveTitle(),
      targetRandomController.resolveTitle(),
    ]);
    await executeSolve({
      startTitle,
      targetTitle,
    });
  });

  updateSolveButtonState();
}

void initializeHomePage();
