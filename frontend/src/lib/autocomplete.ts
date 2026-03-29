import { WikipediaSearchService, type WikipediaSearchResult } from "./wikipedia-search";

interface TitleAutocompleteOptions {
  inputElement: HTMLInputElement;
  suggestionListElement: HTMLElement;
}

export function attachTitleAutocomplete(options: TitleAutocompleteOptions): void {
  const { inputElement, suggestionListElement } = options;
  const searchService = new WikipediaSearchService();

  let activeIndex = -1;
  let currentResults: WikipediaSearchResult[] = [];
  let debounceTimer: number | null = null;

  function clearSuggestions(): void {
    activeIndex = -1;
    currentResults = [];
    suggestionListElement.innerHTML = "";
    suggestionListElement.classList.add("hidden");
  }

  async function applySelection(selectedTitle: string): Promise<void> {
    const resolution = await searchService.resolveTitle(selectedTitle);
    inputElement.value = resolution.canonicalTitle ?? selectedTitle;
    inputElement.dispatchEvent(new Event("input", { bubbles: true }));
    clearSuggestions();
  }

  function renderSuggestions(results: WikipediaSearchResult[]): void {
    currentResults = results;
    activeIndex = -1;

    if (results.length === 0) {
      clearSuggestions();
      return;
    }

    suggestionListElement.innerHTML = results
      .map(
        (result, index) => `
          <button
            class="suggestion-item"
            type="button"
            data-index="${index}"
            role="option"
            aria-selected="false"
          >
            <span class="suggestion-title">${escapeHtml(result.title)}</span>
            <span class="suggestion-description">${escapeHtml(result.description)}</span>
          </button>
        `,
      )
      .join("");

    suggestionListElement.classList.remove("hidden");

    suggestionListElement.querySelectorAll<HTMLButtonElement>(".suggestion-item").forEach((button) => {
      button.addEventListener("mousedown", (event) => {
        event.preventDefault();
      });
      button.addEventListener("click", () => {
        const index = Number(button.dataset.index);
        const result = currentResults[index];
        if (result !== undefined) {
          void applySelection(result.title);
        }
      });
    });
  }

  function syncActiveSuggestion(): void {
    const buttons = suggestionListElement.querySelectorAll<HTMLButtonElement>(".suggestion-item");
    buttons.forEach((button, index) => {
      const isActive = index === activeIndex;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-selected", String(isActive));
    });
  }

  async function performSearch(): Promise<void> {
    const query = inputElement.value.trim();
    if (query.length < 2) {
      clearSuggestions();
      return;
    }

    suggestionListElement.innerHTML = '<div class="suggestion-loading">Searching Wikipedia</div>';
    suggestionListElement.classList.remove("hidden");

    const results = await searchService.search(query);
    if (query !== inputElement.value.trim()) {
      return;
    }
    renderSuggestions(results);
  }

  inputElement.addEventListener("input", () => {
    if (debounceTimer !== null) {
      window.clearTimeout(debounceTimer);
    }
    debounceTimer = window.setTimeout(() => {
      void performSearch();
    }, 120);
  });

  inputElement.addEventListener("focus", () => {
    if (currentResults.length > 0) {
      suggestionListElement.classList.remove("hidden");
    }
  });

  inputElement.addEventListener("blur", () => {
    window.setTimeout(() => {
      clearSuggestions();
      searchService.cancel();
    }, 120);
  });

  inputElement.addEventListener("keydown", (event) => {
    if (currentResults.length === 0) {
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      activeIndex = (activeIndex + 1) % currentResults.length;
      syncActiveSuggestion();
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      activeIndex = activeIndex <= 0 ? currentResults.length - 1 : activeIndex - 1;
      syncActiveSuggestion();
      return;
    }

    if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      const result = currentResults[activeIndex];
      if (result !== undefined) {
        void applySelection(result.title);
      }
      return;
    }

    if (event.key === "Escape") {
      clearSuggestions();
    }
  });
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
