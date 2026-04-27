import { WikipediaRandomService } from "./random-pages";

export interface RandomTitleFieldController {
  setDisabled(disabled: boolean): void;
  setValue(title: string): void;
  resolveTitle(): Promise<string>;
}

export function createRandomTitleField(options: {
  inputElement: HTMLInputElement;
  buttonElement: HTMLButtonElement;
  boxElement: HTMLElement;
  randomService: WikipediaRandomService;
  onValueChange?: () => void;
  onCommit?: () => void;
}): RandomTitleFieldController {
  const { inputElement, buttonElement, boxElement, randomService, onValueChange, onCommit } = options;
  const defaultPlaceholder = inputElement.placeholder;
  let cyclingCallback: ((title: string) => void) | null = null;
  let currentDisplayedTitle = "";
  let isRandomizing = false;

  function commitTitle(title: string): string {
    const resolvedTitle = title.trim();
    if (!resolvedTitle) {
      return "";
    }
    inputElement.value = resolvedTitle;
    inputElement.placeholder = defaultPlaceholder;
    currentDisplayedTitle = resolvedTitle;
    stopCycling();
    onValueChange?.();
    onCommit?.();
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
    onValueChange?.();
    try {
      const title = await randomService.startSlotMachine((candidateTitle, spinning) => {
        currentDisplayedTitle = candidateTitle;
        if (spinning) {
          inputElement.placeholder = candidateTitle;
          return;
        }
        commitTitle(candidateTitle);
      });
      commitTitle(title);
    } finally {
      isRandomizing = false;
      boxElement.classList.remove("is-randomizing");
      buttonElement.disabled = false;
      if (inputElement.value.trim() === "") {
        startCycling();
      }
    }
  }

  buttonElement.addEventListener("click", () => {
    void randomizeTitle();
  });
  inputElement.addEventListener("focus", stopCycling);
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
    onValueChange?.();
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
      return commitTitle(await randomService.getRandomTitle());
    },
  };
}
