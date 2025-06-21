// Main entry point for Wiki Arena event-driven frontend
import { WebSocketClient } from './websocket.js';
import { GameSequenceManager } from './game-sequence.js';
import { UIController } from './ui-controller.js';
import { PageGraphRenderer } from './page-graph-renderer.js';
import { StartGameRequest, GameSequence } from './types.js';

// =============================================================================
// Main Application Class - Orchestrates all components
// =============================================================================

class WikiArenaApp {
  private websocketClient: WebSocketClient;
  private gameSequenceManager: GameSequenceManager;
  private uiController: UIController;
  private pageGraphRenderer: PageGraphRenderer;
  private unsubscribeFunctions: (() => void)[] = [];

  constructor() {
    console.log('🚀 Wiki Arena Frontend initializing (page-centric architecture)...');

    // Initialize components
    this.gameSequenceManager = new GameSequenceManager();
    this.uiController = new UIController();
    this.pageGraphRenderer = new PageGraphRenderer('graph-canvas');
    
    // Initialize WebSocket client (but don't connect yet)
    // Note: We'll set the URL when we start a game and get a game ID
    this.websocketClient = new WebSocketClient({
      url: '', // Will be set when starting a game
      reconnectInterval: 3000,
      maxReconnectAttempts: 5
    });

    this.setupEventFlow();
    this.setupUIHandlers();

    // Ensure graph renderer has correct initial dimensions
    setTimeout(() => {
      this.pageGraphRenderer.resize();
    }, 100);

    console.log('✅ Wiki Arena Frontend ready');
  }

  // =============================================================================
  // Event Flow Setup - Wire components together
  // =============================================================================

  private setupEventFlow(): void {
    // WebSocket events → Game Sequence Manager
    const unsubscribeWebSocket = this.websocketClient.onMessage(event => {
      this.gameSequenceManager.handleEvent(event);
    });

    // WebSocket status → UI Controller
    const unsubscribeStatus = this.websocketClient.onStatusChange(status => {
      this.uiController.updateConnectionStatus(status);
    });

    // Game Sequence → Page Graph Renderer
    const unsubscribePageGraph = this.gameSequenceManager.subscribe(() => {
      const pageGraphData = this.gameSequenceManager.getVisualizationData();
      this.pageGraphRenderer.updateFromPageGraphData(pageGraphData);
    });

    // Game Sequence → UI Controller (with stepping info)
    const unsubscribeSequenceUI = this.gameSequenceManager.subscribe(sequence => {
      // Convert GameSequence to legacy GameState format for UI compatibility
      const legacyState = this.convertSequenceToLegacyState(sequence);
      
      // Get stepping information from GameSequenceManager
      const steppingInfo = {
        currentMoveIndex: sequence.currentPageIndex,
        viewingMoveIndex: sequence.viewingPageIndex,
        renderingMode: sequence.renderingMode,
        canStepForward: this.gameSequenceManager.canStepForward(),
        canStepBackward: this.gameSequenceManager.canStepBackward()
      };
      
      this.uiController.updateGameState(legacyState, steppingInfo);
    });

    // Store unsubscribe functions for cleanup
    this.unsubscribeFunctions.push(
      unsubscribeWebSocket,
      unsubscribeStatus,
      unsubscribePageGraph,
      unsubscribeSequenceUI
    );

    console.log('✅ Event flow setup complete (page-centric architecture)');
  }

  // TODO(hunter): refactor UI to use new GameSequence data structure and remove old GameState
  private convertSequenceToLegacyState(sequence: GameSequence): any {
    // Convert the page-centric GameSequence to legacy GameState format for UI compatibility
    const currentPageState = sequence.pageStates[sequence.viewingPageIndex];
    const moves = sequence.pageStates.slice(1).map((state) => ({
      from_page_title: state.visitedFromPage || '',
      to_page_title: state.pageTitle,
      step: state.moveIndex,
      distanceChange: state.distanceChange
    }));

    return {
      gameId: sequence.gameId,
      status: sequence.status,
      startPage: sequence.startPage,
      targetPage: sequence.targetPage,
      currentPage: currentPageState?.pageTitle || null,
      moves: moves,
      optimalPaths: currentPageState?.optimalPaths || [],
      currentDistance: currentPageState?.distanceToTarget || null,
      initialOptimalDistance: sequence.initialOptimalDistance,
      totalMoves: sequence.pageStates.length - 1, // Subtract 1 for start page
    };
  }

  private setupUIHandlers(): void {
    this.uiController.setupEventListeners({
      onStartGame: () => this.handleStartGame(),
      onStepBackward: () => this.handleStepBackward(),
      onStepForward: () => this.handleStepForward(),
      onEnterLiveMode: () => this.handleEnterLiveMode(),
      onStepToMove: (moveIndex: number) => this.handleStepToMove(moveIndex)
    });
    
    // Setup info panel toggle
    this.setupInfoPanelToggle();
    
    // Setup window resize handler
    this.setupWindowResize();
  }
  
  private setupInfoPanelToggle(): void {
    const toggleButton = document.getElementById('info-toggle');
    const infoPanel = document.getElementById('info-panel');
    
    if (toggleButton && infoPanel) {
      let isCollapsed = false;
      
      toggleButton.addEventListener('click', () => {
        isCollapsed = !isCollapsed;
        
        if (isCollapsed) {
          infoPanel.classList.add('collapsed');
          toggleButton.textContent = '📊';
          toggleButton.title = 'Show info panel';
        } else {
          infoPanel.classList.remove('collapsed');
          toggleButton.textContent = '✖️';
          toggleButton.title = 'Hide info panel';
        }
      });
    }
  }
  
  private setupWindowResize(): void {
    let resizeTimeout: number;
    
    window.addEventListener('resize', () => {
      // Debounce resize events
      clearTimeout(resizeTimeout);
      resizeTimeout = window.setTimeout(() => {
        this.pageGraphRenderer.resize();
      }, 100);
    });
  }

  // =============================================================================
  // User Action Handlers
  // =============================================================================

  public async handleStartGame(): Promise<void> {
    console.log('🎲 User requested new game');

    // Show loading state
    this.uiController.showGameStarting();
    this.uiController.setButtonLoading('start-game-btn', true, 'Starting...');

    try {
      // Make API call to start game
      const response = await this.startNewGame();
      
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Game started:', data);
        
        // Extract game ID from response
        const gameId = data.game_id;
        if (!gameId) {
          throw new Error('No game ID returned from server');
        }
        
        // Reset game state for new game
        this.resetGameManagers();
        
        // Connect to game-specific WebSocket
        const gameWebSocketUrl = `ws://localhost:8000/api/games/${gameId}/ws`;
        this.websocketClient.updateUrl(gameWebSocketUrl);
        this.websocketClient.connect();
        
        console.log(`🔌 Connecting to game WebSocket: ${gameWebSocketUrl}`);
      } else {
        const errorText = await response.text();
        throw new Error(`Failed to start game: ${response.status} - ${errorText}`);
      }
    } catch (error) {
      console.error('❌ Failed to start game:', error);
      this.uiController.showError(`Failed to start new game: ${error instanceof Error ? error.message : 'Unknown error'}`);
      this.uiController.updateLoadingState('Click "Start New Game" to try again');
    } finally {
      this.uiController.setButtonLoading('start-game-btn', false);
    }
  }

  public async handleStartCustomGame(startPage: string, targetPage: string): Promise<void> {
    console.log(`🎲 User requested custom game: ${startPage} -> ${targetPage}`);

    // Show loading state
    this.uiController.showGameStarting();
    this.uiController.setButtonLoading('start-game-btn', true, 'Starting...');

    try {
      // Make API call to start custom game
      const response = await this.startCustomGame(startPage, targetPage);
      
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Custom game started:', data);
        
        // Extract game ID from response
        const gameId = data.game_id;
        if (!gameId) {
          throw new Error('No game ID returned from server');
        }
        
        // Reset game state for new game
        this.resetGameManagers();
        
        // Connect to game-specific WebSocket
        const gameWebSocketUrl = `ws://localhost:8000/api/games/${gameId}/ws`;
        this.websocketClient.updateUrl(gameWebSocketUrl);
        this.websocketClient.connect();
        
        console.log(`🔌 Connecting to custom game WebSocket: ${gameWebSocketUrl}`);
      } else {
        const errorText = await response.text();
        throw new Error(`Failed to start custom game: ${response.status} - ${errorText}`);
      }
    } catch (error) {
      console.error('❌ Failed to start custom game:', error);
      this.uiController.showError(`Failed to start custom game: ${error instanceof Error ? error.message : 'Unknown error'}`);
      this.uiController.updateLoadingState('Click "Start New Game" to try again');
    } finally {
      this.uiController.setButtonLoading('start-game-btn', false);
    }
  }

  // =============================================================================
  // Stepping Control Handlers - PAGE-CENTRIC
  // =============================================================================

  public handleStepBackward(): void {
    console.log('⬅️ User stepping backward');
    this.gameSequenceManager.stepBackward();
  }

  public handleStepForward(): void {
    console.log('➡️ User stepping forward');
    this.gameSequenceManager.stepForward();
  }

  public handleEnterLiveMode(): void {
    console.log('🔴 User entering live mode');
    this.gameSequenceManager.enterLiveMode();
  }

  public handleStepToMove(moveIndex: number): void {
    console.log(`🎯 User stepping to page ${moveIndex}`);
    this.gameSequenceManager.goToPageIndex(moveIndex);
  }

  // =============================================================================
  // Helper Methods
  // =============================================================================

  private resetGameManagers(): void {
    this.gameSequenceManager.reset();
  }

  // =============================================================================
  // API Calls
  // =============================================================================

  private async startCustomGame(startPage: string, targetPage: string): Promise<Response> {
    const apiUrl = 'http://localhost:8000/api/games?background=true';
    
    const gameRequest = {
      task_strategy: {
        type: 'custom',
        start_page: startPage,
        target_page: targetPage
      },
      model_name: 'random',
      model_provider: 'random',
      max_steps: 30
    };
    
    return fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(gameRequest)
    });
  }

  private async startNewGame(request: StartGameRequest = {}): Promise<Response> {
    // Use the correct backend API endpoint structure with background query parameter
    const apiUrl = 'http://localhost:8000/api/games?background=true'; // Background as query param
    
    // Create a game request with random task selection strategy
    const gameRequest = {
      task_strategy: {
        type: 'random',
        language: 'en',
        max_retries: 3
      },
      model_name: 'random',
      model_provider: 'random',
      max_steps: 30,
      ...request
    };
    
    return fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(gameRequest)
    });
  }

  // =============================================================================
  // Lifecycle Management
  // =============================================================================

  destroy(): void {
    console.log('🧹 Cleaning up Wiki Arena Frontend');
    
    // Unsubscribe from all events
    this.unsubscribeFunctions.forEach(unsubscribe => unsubscribe());
    this.unsubscribeFunctions = [];
    
    // Disconnect WebSocket
    this.websocketClient.disconnect();
  }

  // =============================================================================
  // Graph Methods
  // =============================================================================

  public centerGraph(): void {
    this.pageGraphRenderer.centerGraph();
  }

  public clearGraph(): void {
    this.pageGraphRenderer.clear();
  }

  // =============================================================================
  // Debug Methods
  // =============================================================================

  debug(): void {
    console.log('🐛 Debug Info:');
    console.log('WebSocket Status:', this.websocketClient.getStatus());
    console.log('Game Sequence:', this.gameSequenceManager.getSequence());
    this.gameSequenceManager.debugState();
    this.uiController.debugElements();
    console.log('Page Graph Renderer:', this.pageGraphRenderer);
  }
}

// =============================================================================
// Application Lifecycle
// =============================================================================

let app: WikiArenaApp | null = null;

function initializeApp(): void {
  if (app) {
    console.warn('⚠️ App already initialized');
    return;
  }

  try {
    app = new WikiArenaApp();
    
    // Make app globally available for debugging
    (window as any).wikiArena = {
      app,
      debug: () => app?.debug(),
      startGame: () => app?.handleStartGame(),
      startCustomGame: (start: string, target: string) => app?.handleStartCustomGame(start, target),
      centerGraph: () => app?.centerGraph(),
      clearGraph: () => app?.clearGraph(),
      // New stepping controls
      stepBackward: () => app?.handleStepBackward(),
      stepForward: () => app?.handleStepForward(),
      enterLiveMode: () => app?.handleEnterLiveMode(),
      stepToMove: (moveIndex: number) => app?.handleStepToMove(moveIndex)
    };
    
    console.log('🎮 Wiki Arena loaded! Use window.wikiArena for debugging.');
  } catch (error) {
    console.error('❌ Failed to initialize app:', error);
  }
}

function destroyApp(): void {
  if (app) {
    app.destroy();
    app = null;
    delete (window as any).wikiArena;
  }
}

// =============================================================================
// DOM Ready Handler
// =============================================================================

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeApp);
} else {
  initializeApp();
}

// Cleanup on page unload
window.addEventListener('beforeunload', destroyApp);

export { WikiArenaApp };