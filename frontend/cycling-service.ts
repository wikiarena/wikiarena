import { modelService, ModelInfo } from './model-service.js';
import { WikipediaRandomService } from './wikipedia-random.js';

class CyclingService {
    private static instance: CyclingService;
    private modelCallbacks: Array<(modelName: string) => void> = [];
    private pageCallbacks: Array<(pageTitle: string) => void> = [];
    
    private models: ModelInfo[] = [];
    private pageTitles: string[] = [];

    private modelIndex: number = 0;
    private pageIndex: number = 0;

    private cycleInterval: number | null = null;
    private isInitialized: boolean = false;
    private readonly cycleTime: number = 1000; // ms
    private randomService: WikipediaRandomService;


    private constructor() {
        this.randomService = new WikipediaRandomService();
        this.initialize();
    }

    public static getInstance(): CyclingService {
        if (!CyclingService.instance) {
            CyclingService.instance = new CyclingService();
        }
        return CyclingService.instance;
    }

    private async initialize(): Promise<void> {
        if (this.isInitialized) return;

        const [models, pages] = await Promise.all([
            this.fetchModels(),
            this.randomService.fetchRandomPages()
        ]);

        this.models = models; // Data is now pre-sorted by the backend
        this.pageTitles = pages.sort(() => Math.random() - 0.5); // Shuffle pages

        this.isInitialized = true;
        
        if (this.models.length > 0 || this.pageTitles.length > 0) {
            this.startCycling();
        }
    }

    private async fetchModels(): Promise<ModelInfo[]> {
        try {
            // Use the singleton model service
            return await modelService.getModels();
        } catch (error) {
            console.error('Failed to load models for cycling:', error);
            return [];
        }
    }

    private startCycling(): void {
        if (this.cycleInterval !== null || !this.isInitialized) return;

        // Cycle through model names and page titles
        this.cycleInterval = window.setInterval(() => {
            // Calculate a dynamic step to ensure visible separation between placeholders
            const modelStep = Math.max(1, Math.floor(this.models.length / (this.modelCallbacks.length + 1)));
            const pageStep = Math.max(1, Math.floor(this.pageTitles.length / (this.pageCallbacks.length + 1)));

            // Broadcast to model callbacks
            if (this.modelCallbacks.length > 0 && this.models.length > 0) {
                this.modelCallbacks.forEach((cb, i) => {
                    const modelIndexForCallback = (this.modelIndex + i * modelStep) % this.models.length;
                    const modelName = this.models[modelIndexForCallback].name;
                    cb(modelName);
                });
            }

            // Broadcast to page callbacks
            if (this.pageCallbacks.length > 0 && this.pageTitles.length > 0) {
                this.pageCallbacks.forEach((cb, i) => {
                    const pageIndexForCallback = (this.pageIndex + i * pageStep) % this.pageTitles.length;
                    const pageTitle = this.pageTitles[pageIndexForCallback];
                    cb(pageTitle);
                });
            }

            // Advance base indices for next tick, ensuring they loop correctly
            if (this.models.length > 0) {
                this.modelIndex = (this.modelIndex + 1) % this.models.length;
            }
            if (this.pageTitles.length > 0) {
                this.pageIndex = (this.pageIndex + 1) % this.pageTitles.length;
            }
        }, this.cycleTime);
    }

    private stopCycling(): void {
        if (this.cycleInterval !== null) {
            window.clearInterval(this.cycleInterval);
            this.cycleInterval = null;
        }
    }

    public registerModelCallback(callback: (modelName: string) => void): void {
        if (this.modelCallbacks.includes(callback)) return;

        // Immediately provide an offset value
        if (this.models.length > 0) {
            const modelStep = Math.max(1, Math.floor(this.models.length / (this.modelCallbacks.length + 2)));
            const nextIndex = (this.modelIndex + this.modelCallbacks.length * modelStep) % this.models.length;
            callback(this.models[nextIndex].name);
        }
        this.modelCallbacks.push(callback);

        if (this.modelCallbacks.length === 1 && this.pageCallbacks.length === 0) {
            this.startCycling();
        }
    }

    public unregisterModelCallback(callback: (modelName: string) => void): void {
        this.modelCallbacks = this.modelCallbacks.filter(cb => cb !== callback);
        if (this.modelCallbacks.length === 0 && this.pageCallbacks.length === 0) {
            this.stopCycling();
        }
    }

    public registerPageCallback(callback: (pageTitle: string) => void): void {
        if (this.pageCallbacks.includes(callback)) return;

        // Immediately provide an offset value
        if (this.pageTitles.length > 0) {
            const pageStep = Math.max(1, Math.floor(this.pageTitles.length / (this.pageCallbacks.length + 2)));
            const nextIndex = (this.pageIndex + this.pageCallbacks.length * pageStep) % this.pageTitles.length;
            callback(this.pageTitles[nextIndex]);
        }
        this.pageCallbacks.push(callback);

        if (this.pageCallbacks.length === 1 && this.modelCallbacks.length === 0) {
            this.startCycling();
        }
    }

    public unregisterPageCallback(callback: (pageTitle: string) => void): void {
        this.pageCallbacks = this.pageCallbacks.filter(cb => cb !== callback);
        if (this.modelCallbacks.length === 0 && this.pageCallbacks.length === 0) {
            this.stopCycling();
        }
    }
}

export const cyclingService = CyclingService.getInstance(); 