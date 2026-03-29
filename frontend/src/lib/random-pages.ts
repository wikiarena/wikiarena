import { loadRandomPageTitles } from "./api";

interface RandomPageCache {
  snapshotId: string;
  titles: string[];
  cachedAtMs: number;
}

type RandomTitleCallback = (title: string) => void;

const sharedRandomState: {
  cache: RandomPageCache | null;
  refreshPromise: Promise<string[]> | null;
  cyclingCallbacks: RandomTitleCallback[];
  cycleInterval: number | null;
  pageIndex: number;
} = {
  cache: null,
  refreshPromise: null,
  cyclingCallbacks: [],
  cycleInterval: null,
  pageIndex: 0,
};

const PLACEHOLDER_CYCLE_INTERVAL_MS = 1000;

export class WikipediaRandomService {
  private slotTimer: number | null = null;
  private readonly cacheDurationMs = 10 * 60 * 1000;
  private readonly randomPageCount = 200;
  private readonly fallbackTitles = [
    "Wikipedia",
    "Earth",
    "Computer science",
    "Mathematics",
    "Philosophy",
    "Jazz",
  ];

  async fetchRandomTitles(options: { force?: boolean } = {}): Promise<string[]> {
    const shouldUseCache = !options.force;
    if (
      shouldUseCache &&
      sharedRandomState.cache !== null &&
      Date.now() - sharedRandomState.cache.cachedAtMs < this.cacheDurationMs
    ) {
      return sharedRandomState.cache.titles;
    }

    if (sharedRandomState.refreshPromise !== null) {
      return sharedRandomState.refreshPromise;
    }

    const refreshPromise = this.fetchAndCacheRandomTitles();
    sharedRandomState.refreshPromise = refreshPromise.finally(() => {
      if (sharedRandomState.refreshPromise === refreshPromise) {
        sharedRandomState.refreshPromise = null;
      }
    });
    return sharedRandomState.refreshPromise;
  }

  refreshRandomTitlesInBackground(): void {
    void this.fetchRandomTitles({
      force: true,
    });
  }

  async getRandomTitle(): Promise<string> {
    const titles = await this.fetchRandomTitles();
    if (titles.length === 0) {
      return this.fallbackTitles[0];
    }

    return titles[Math.floor(Math.random() * titles.length)];
  }

  async getDistinctRandomTitles(
    count: number,
    excludedTitles: string[] = [],
  ): Promise<string[]> {
    const initialTitles = await this.fetchRandomTitles();
    let pickedTitles = this.pickDistinctTitles(
      initialTitles,
      count,
      excludedTitles,
    );
    if (pickedTitles.length === count) {
      return pickedTitles;
    }

    const refreshedTitles = await this.fetchRandomTitles({
      force: true,
    });
    pickedTitles = this.pickDistinctTitles(
      refreshedTitles,
      count,
      excludedTitles,
    );

    const normalizedChosenTitles = new Set(
      pickedTitles.map((title) => this.normalizeTitle(title)),
    );
    const normalizedExcludedTitles = new Set(
      excludedTitles.map((title) => this.normalizeTitle(title)),
    );
    for (const fallbackTitle of this.fallbackTitles) {
      const normalizedFallbackTitle = this.normalizeTitle(fallbackTitle);
      if (normalizedChosenTitles.has(normalizedFallbackTitle)) {
        continue;
      }
      if (normalizedExcludedTitles.has(normalizedFallbackTitle)) {
        continue;
      }
      pickedTitles.push(fallbackTitle);
      normalizedChosenTitles.add(normalizedFallbackTitle);
      if (pickedTitles.length === count) {
        break;
      }
    }

    return pickedTitles.slice(0, count);
  }

  registerCyclingCallback(callback: RandomTitleCallback): void {
    if (sharedRandomState.cyclingCallbacks.includes(callback)) {
      return;
    }

    sharedRandomState.cyclingCallbacks.push(callback);
    void this.initializeCyclingCallback(callback);
    this.startCycling();
  }

  unregisterCyclingCallback(callback: RandomTitleCallback): void {
    sharedRandomState.cyclingCallbacks = sharedRandomState.cyclingCallbacks.filter(
      (registeredCallback) => registeredCallback !== callback,
    );
    if (sharedRandomState.cyclingCallbacks.length === 0) {
      this.stopCycling();
    }
  }

  async startSlotMachine(
    onTick: (title: string, isSpinning: boolean) => void,
  ): Promise<string> {
    const titles = await this.fetchRandomTitles();
    if (titles.length === 0) {
      const fallbackTitle = this.fallbackTitles[0];
      onTick(fallbackTitle, false);
      return fallbackTitle;
    }

    this.stopSlotMachine();

    return new Promise((resolve) => {
      let currentIndex = Math.floor(Math.random() * titles.length);
      let spinCount = 0;
      const totalSpins = 20 + Math.floor(Math.random() * 10);

      const nextDelayMs = (currentSpin: number): number => {
        const progress = currentSpin / totalSpins;
        if (progress < 0.6) {
          return 50 + Math.random() * 30;
        }
        if (progress < 0.85) {
          return 80 + (progress - 0.6) * 400;
        }
        return 180 + (progress - 0.85) * 800;
      };

      const spin = (): void => {
        currentIndex = (currentIndex + 1) % titles.length;
        spinCount += 1;

        const currentTitle = titles[currentIndex];
        const isSpinning = spinCount < totalSpins;
        onTick(currentTitle, isSpinning);

        if (!isSpinning) {
          this.slotTimer = null;
          resolve(currentTitle);
          return;
        }

        this.slotTimer = window.setTimeout(spin, nextDelayMs(spinCount));
      };

      onTick(titles[currentIndex], true);
      this.slotTimer = window.setTimeout(spin, nextDelayMs(0));
    });
  }

  stopSlotMachine(): void {
    if (this.slotTimer !== null) {
      window.clearTimeout(this.slotTimer);
      this.slotTimer = null;
    }
  }

  private async fetchAndCacheRandomTitles(): Promise<string[]> {
    try {
      const payload = await loadRandomPageTitles(this.randomPageCount);
      const titles = this.shuffleTitles(
        payload.titles
          .map((title) => title.trim())
          .filter((title) => title.length > 0),
      );

      sharedRandomState.cache = {
        snapshotId: payload.snapshot_id,
        titles,
        cachedAtMs: Date.now(),
      };
      if (sharedRandomState.pageIndex >= titles.length) {
        sharedRandomState.pageIndex = 0;
      }
      return titles;
    } catch {
      if (sharedRandomState.cache !== null) {
        return sharedRandomState.cache.titles;
      }

      const titles = [...this.fallbackTitles];
      if (sharedRandomState.cache === null) {
        sharedRandomState.cache = {
          snapshotId: "fallback",
          titles,
          cachedAtMs: Date.now(),
        };
      }
      return titles;
    }
  }

  private async initializeCyclingCallback(callback: RandomTitleCallback): Promise<void> {
    const titles = await this.fetchRandomTitles();
    const callbackIndex = sharedRandomState.cyclingCallbacks.indexOf(callback);
    if (callbackIndex < 0 || titles.length === 0) {
      return;
    }

    const pageStep = Math.max(
      1,
      Math.floor(titles.length / (sharedRandomState.cyclingCallbacks.length + 1)),
    );
    const nextIndex = (sharedRandomState.pageIndex + callbackIndex * pageStep) % titles.length;
    callback(titles[nextIndex]);
  }

  private startCycling(): void {
    if (sharedRandomState.cycleInterval !== null) {
      return;
    }

    void this.fetchRandomTitles();
    sharedRandomState.cycleInterval = window.setInterval(() => {
      const titles = sharedRandomState.cache?.titles ?? [];
      if (sharedRandomState.cyclingCallbacks.length === 0 || titles.length === 0) {
        return;
      }

      const pageStep = Math.max(
        1,
        Math.floor(titles.length / (sharedRandomState.cyclingCallbacks.length + 1)),
      );

      sharedRandomState.cyclingCallbacks.forEach((callback, index) => {
        const titleIndex = (sharedRandomState.pageIndex + index * pageStep) % titles.length;
        callback(titles[titleIndex]);
      });

      sharedRandomState.pageIndex = (sharedRandomState.pageIndex + 1) % titles.length;
    }, PLACEHOLDER_CYCLE_INTERVAL_MS);
  }

  private stopCycling(): void {
    if (sharedRandomState.cycleInterval !== null) {
      window.clearInterval(sharedRandomState.cycleInterval);
      sharedRandomState.cycleInterval = null;
    }
  }

  private pickDistinctTitles(
    titles: string[],
    count: number,
    excludedTitles: string[],
  ): string[] {
    const normalizedExcludedTitles = new Set(
      excludedTitles.map((title) => this.normalizeTitle(title)),
    );
    const shuffledTitles = this.shuffleTitles(titles);
    const pickedTitles: string[] = [];
    const normalizedPickedTitles = new Set<string>();

    for (const title of shuffledTitles) {
      const normalizedTitle = this.normalizeTitle(title);
      if (normalizedExcludedTitles.has(normalizedTitle)) {
        continue;
      }
      if (normalizedPickedTitles.has(normalizedTitle)) {
        continue;
      }
      pickedTitles.push(title);
      normalizedPickedTitles.add(normalizedTitle);
      if (pickedTitles.length === count) {
        break;
      }
    }

    return pickedTitles;
  }

  private normalizeTitle(title: string): string {
    return title.trim().toLowerCase();
  }

  private shuffleTitles(titles: string[]): string[] {
    const shuffledTitles = [...titles];
    for (let index = shuffledTitles.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(Math.random() * (index + 1));
      [shuffledTitles[index], shuffledTitles[swapIndex]] = [shuffledTitles[swapIndex], shuffledTitles[index]];
    }
    return shuffledTitles;
  }
}
