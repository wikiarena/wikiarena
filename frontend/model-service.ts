import { config } from './config.js';

export interface ModelInfo {
    id: string;
    name: string;
    provider: string;
    icon_slug: string;
    input_cost_per_1m_tokens: number;
    output_cost_per_1m_tokens: number;
}

class ModelService {
    private static instance: ModelService;
    private models: ModelInfo[] = [];
    private modelsPromise: Promise<void> | null = null;

    private constructor() {
        this.modelsPromise = this.loadModels();
    }

    public static getInstance(): ModelService {
        if (!ModelService.instance) {
            ModelService.instance = new ModelService();
        }
        return ModelService.instance;
    }

    private async loadModels(): Promise<void> {
        try {
            console.log('Fetching models from backend API...');
            const response = await fetch(`${config.apiBaseUrl}/api/models`);
            if (!response.ok) {
                throw new Error(`Failed to fetch models: ${response.statusText}`);
            }
            this.models = await response.json();
            console.log(`Successfully loaded ${this.models.length} models.`);
        } catch (error) {
            console.error('Error loading models:', error);
            // In case of an error, models will be an empty array
            this.models = [];
        }
    }

    public async getModels(): Promise<ModelInfo[]> {
        // Ensure that the models are loaded before returning them
        if (this.modelsPromise) {
            await this.modelsPromise;
        }
        return this.models;
    }

    public async getModelById(modelId: string): Promise<ModelInfo | undefined> {
        await this.getModels(); // Ensure models are loaded
        return this.models.find(model => model.id === modelId);
    }
}

// Export a singleton instance
export const modelService = ModelService.getInstance(); 