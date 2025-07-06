import { WikipediaRandomService } from './wikipedia-random.js';
import type { ModelOption, ModelInfo } from './model-selector.js';

class CyclingService {
    private randomService = new WikipediaRandomService();
    private pageCallbacks: Array<(title: string) => void> = [];
    private modelCallbacks: Array<(title: string) => void> = [];
    
    private pageTitles: string[] = [];
    private modelNames: string[] = [];
    
    private pageIndex = 0;
    private modelIndex = 0;
    
    private cycleInterval: NodeJS.Timeout | null = null;
    private isInitialized = false;
    private readonly INTERVAL_MS = 500;

    constructor() {
        // Delay initialization to avoid blocking main thread
        setTimeout(() => this.initialize(), 0);
    }

    private async initialize(): Promise<void> {
        if (this.isInitialized) return;

        const [pages, models] = await Promise.all([
            this.randomService.fetchRandomPages(),
            this.fetchModels()
        ]);
        
        this.pageTitles = pages.sort(() => Math.random() - 0.5);
        this.modelNames = models.map(m => m.id).sort(() => Math.random() - 0.5);
        
        if (this.pageTitles.length > 0) {
            this.pageIndex = Math.floor(Math.random() * this.pageTitles.length);
        }
        if (this.modelNames.length > 0) {
            this.modelIndex = Math.floor(Math.random() * this.modelNames.length);
        }

        this.isInitialized = true;
        
        // If callbacks were registered before initialization, start cycling
        if (this.pageCallbacks.length > 0 || this.modelCallbacks.length > 0) {
            this.startCycling();
        }
    }

    private async fetchModels(): Promise<ModelOption[]> {
        try {
            const response = await fetch('./models.json');
            const modelsData: Record<string, ModelInfo> = await response.json();
            
            return Object.entries(modelsData).map(([id, info]) => ({
                id,
                provider: info.provider,
                inputCost: info.input_cost_per_1m_tokens,
                outputCost: info.output_cost_per_1m_tokens,
                maxTokens: info.default_settings.max_tokens,
                iconPath: '' // Not needed for cycling service
            }));
        } catch (error) {
            console.error('Failed to load models for cycling:', error);
            return [];
        }
    }

    private startCycling(): void {
        if (this.cycleInterval || !this.isInitialized) return;

        this.cycleInterval = setInterval(() => {
            this.broadcastUpdate();
        }, this.INTERVAL_MS);
    }
    
    private stopCycling(): void {
        if (this.cycleInterval) {
            clearInterval(this.cycleInterval);
            this.cycleInterval = null;
        }
    }

    private broadcastUpdate(): void {
        // Broadcast to page callbacks
        if (this.pageCallbacks.length > 0 && this.pageTitles.length > 0) {
            this.pageCallbacks.forEach((cb, i) => {
                const pageIndexForCallback = (this.pageIndex + i) % this.pageTitles.length;
                const pageTitle = this.pageTitles[pageIndexForCallback];
                cb(pageTitle);
            });
        }
        
        // Broadcast to model callbacks
        if (this.modelCallbacks.length > 0 && this.modelNames.length > 0) {
            this.modelCallbacks.forEach((cb, i) => {
                const modelIndexForCallback = (this.modelIndex + i) % this.modelNames.length;
                const modelName = this.modelNames[modelIndexForCallback];
                cb(modelName);
            });
        }

        // Advance base indices for next tick
        this.pageIndex = (this.pageIndex + 1) % this.pageTitles.length;
        this.modelIndex = (this.modelIndex + 1) % this.modelNames.length;
    }

    public registerPageCallback(callback: (title: string) => void): void {
        if (!this.pageCallbacks.includes(callback)) {
            this.pageCallbacks.push(callback);
        }
        this.startCycling();
    }

    public unregisterPageCallback(callback: (title: string) => void): void {
        this.pageCallbacks = this.pageCallbacks.filter(cb => cb !== callback);
        this.checkAndStopCycling();
    }

    public registerModelCallback(callback: (title: string) => void): void {
        if (!this.modelCallbacks.includes(callback)) {
            this.modelCallbacks.push(callback);
        }
        this.startCycling();
    }

    public unregisterModelCallback(callback: (title: string) => void): void {
        this.modelCallbacks = this.modelCallbacks.filter(cb => cb !== callback);
        this.checkAndStopCycling();
    }

    private checkAndStopCycling(): void {
        if (this.pageCallbacks.length === 0 && this.modelCallbacks.length > 0) {
            // If only model callbacks are left, we can just cycle models
            // This case is simple, so we just check if both are empty
        }

        if (this.pageCallbacks.length === 0 && this.modelCallbacks.length === 0) {
            this.stopCycling();
        }
    }
}

export const cyclingService = new CyclingService(); 