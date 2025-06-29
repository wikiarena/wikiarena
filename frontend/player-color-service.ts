import { PageNode, ModelConfig } from './types.js';

/**
 * Centralized service for managing player colors across the entire visualization.
 * Uses provider-based brand colors for consistent theming.
 */
export class PlayerColorService {
  private static instance: PlayerColorService;
  private gameColorMap = new Map<string, string>();
  private gameDisplayNames = new Map<string, string>();
  private modelConfigs: Record<string, ModelConfig> = {};
  private providerColorCounters = new Map<string, number>();
  
  // Provider-based color palettes using brand colors
  private providerColorPalettes: Record<string, string[]> = {
    'anthropic': ['#D97757', '#CC785C', '#D4A27F'], // Coral, Book Cloth, Kraft
    // 'openai': ['#000000', '#FFFFFF', '#6B7280'],    // Black, white, medium gray
    'google': ['#1C69FF', '#4796E3', '#9177C7'],    // Focus blue, Gemini purple, Error red/pink
    'random': [], // Will be populated with random colors from other providers
  };

  /**
   * Get singleton instance of the color service
   */
  static getInstance(): PlayerColorService {
    if (!this.instance) {
      this.instance = new PlayerColorService();
    }
    return this.instance;
  }

  /**
   * Initialize the service by loading model configurations
   */
  async initialize(): Promise<void> {
    try {
      console.log('🎨 PlayerColorService: Loading model configurations...');
      
      // Load models.json - assuming it's served from the root
      const response = await fetch('/models.json');
      if (!response.ok) {
        throw new Error(`Failed to load models.json: ${response.statusText}`);
      }
      
      this.modelConfigs = await response.json();
      console.log('🎨 Loaded model configurations:', Object.keys(this.modelConfigs));
      
      // Populate random provider colors
      this.populateRandomColors();
      
    } catch (error) {
      console.error('🎨 Failed to load model configurations:', error);
      // Fallback to empty config - service will still work with default colors
      this.modelConfigs = {};
    }
  }

  /**
   * Populate the random provider with colors from all other providers
   */
  private populateRandomColors(): void {
    const allColors: string[] = [];
    Object.entries(this.providerColorPalettes).forEach(([provider, colors]) => {
      if (provider !== 'random') {
        allColors.push(...colors);
      }
    });
    
    // Shuffle the colors for random selection
    for (let i = allColors.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [allColors[i], allColors[j]] = [allColors[j], allColors[i]];
    }
    
    this.providerColorPalettes.random = allColors;
    console.log('🎨 Random provider colors populated:', allColors);
  }

  /**
   * Extract model key from game ID (game IDs start with model key)
   */
  private extractModelKeyFromGameId(gameId: string): string {
    // Game IDs format: {model_key}_{timestamp}_{uuid}
    // We need to find the longest matching model key
    const modelKeys = Object.keys(this.modelConfigs);
    
    // Sort by length descending to match longest first (handles cases like gpt-4o vs gpt-4o-mini)
    const sortedKeys = modelKeys.sort((a, b) => b.length - a.length);
    
    for (const modelKey of sortedKeys) {
      if (gameId.startsWith(modelKey + '_')) {
        return modelKey;
      }
    }
    
    console.warn(`🎨 Could not extract model key from game ID: ${gameId}`);
    return 'unknown';
  }

  /**
   * Get provider for a model key
   */
  private getProviderForModelKey(modelKey: string): string {
    const modelConfig = this.modelConfigs[modelKey];
    if (!modelConfig) {
      console.warn(`🎨 No configuration found for model: ${modelKey}`);
      return 'unknown';
    }
    return modelConfig.provider;
  }

  /**
   * Get the next color for a provider (cycles through the provider's palette)
   */
  private getNextColorForProvider(provider: string): string {
    const palette = this.providerColorPalettes[provider];
    if (!palette || palette.length === 0) {
      console.warn(`🎨 No color palette found for provider: ${provider}`);
      return '#64748b'; // Fallback gray
    }
    
    const currentCount = this.providerColorCounters.get(provider) || 0;
    const color = palette[currentCount % palette.length];
    this.providerColorCounters.set(provider, currentCount + 1);
    
    return color;
  }

  /**
   * Assign colors to games when a new task is created
   */
  assignColorsForTask(gameIds: string[]): void {
    console.log(`🎨 PlayerColorService: Assigning colors for ${gameIds.length} games`);
    
    // Reset provider counters for this task
    this.providerColorCounters.clear();
    
    gameIds.forEach((gameId) => {
      const modelKey = this.extractModelKeyFromGameId(gameId);
      const provider = this.getProviderForModelKey(modelKey);
      const color = this.getNextColorForProvider(provider);
      
      this.gameColorMap.set(gameId, color);
      this.gameDisplayNames.set(gameId, `${modelKey}`); // Use model key as display name
      
      console.log(`🎨 Assigned ${color} to ${gameId} (${provider}/${modelKey})`);
    });
  }

  /**
   * Get the assigned color for a specific game
   */
  getColorForGame(gameId: string): string {
    return this.gameColorMap.get(gameId) || '#64748b'; // Default gray
  }

  /**
   * Get the display name for a specific game
   */
  getDisplayName(gameId: string): string {
    return this.gameDisplayNames.get(gameId) || 'Unknown Player';
  }

  /**
   * Get the icon path for a specific game
   */
  getIconForGame(gameId: string): string {
    const modelKey = this.extractModelKeyFromGameId(gameId);
    const provider = this.getProviderForModelKey(modelKey);
    return this.getIconForProvider(provider);
  }

  /**
   * Get the icon path for a specific provider
   */
  getIconForProvider(provider: string): string {
    const iconMap: Record<string, string> = {
      'anthropic': '/assets/icons/claude-color.svg',
      'openai': '/assets/icons/openai.svg',
      'google': '/assets/icons/gemini-color.svg',
      'random': '/assets/icons/dice.svg',
    };
    
    return iconMap[provider] || '/assets/icons/question-mark.svg'; // Fallback to question mark for unknown providers
  }

  /**
   * Get the appropriate color for a page node based on player visits
   * Priority: start/target nodes use solid colors, visited nodes use player colors
   */
  getNodeColor(pageNode: PageNode): string {
    // Start and target nodes use solid colors
    if (pageNode.type === 'start') {
      return '#10b981'; // Solid green
    }
    if (pageNode.type === 'target') {
      return '#f59e0b'; // Solid orange
    }
    
    // Optimal path nodes keep their neutral color
    if (pageNode.type === 'optimal_path') {
      return '#374151';
    }
    
    // Visited nodes use player colors
    if (pageNode.type === 'visited' && pageNode.visits.length > 0) {
      // Use the first visit's player color (in multi-visit scenarios, first player takes precedence)
      const firstVisit = pageNode.visits[0];
      return this.getColorForGame(firstVisit.gameId);
    }
    
    // Fallback
    return '#64748b';
  }

  /**
   * Get all currently assigned game colors (useful for debugging)
   */
  getAllGameColors(): Map<string, string> {
    return new Map(this.gameColorMap);
  }

  /**
   * Get provider information for debugging
   */
  getProviderInfo(): Record<string, any> {
    return {
      modelConfigs: this.modelConfigs,
      providerColorPalettes: this.providerColorPalettes,
      providerColorCounters: Array.from(this.providerColorCounters.entries())
    };
  }

  /**
   * Reset all color assignments (called when starting a new task)
   */
  reset(): void {
    console.log('🎨 PlayerColorService: Resetting color assignments');
    this.gameColorMap.clear();
    this.gameDisplayNames.clear();
    this.providerColorCounters.clear();
  }

  /**
   * Debug method to log current state
   */
  debugState(): void {
    console.log('🎨 PlayerColorService Debug State:');
    console.log('Game Colors:', Array.from(this.gameColorMap.entries()));
    console.log('Display Names:', Array.from(this.gameDisplayNames.entries()));
    console.log('Provider Info:', this.getProviderInfo());
  }
}

// Export a convenience function to get the singleton instance
export const playerColorService = PlayerColorService.getInstance(); 