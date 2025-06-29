// Main entry point for Wiki Arena event-driven frontend
import { TaskManager } from './task-manager.js';
import { TaskConnectionManager } from './task-connection-manager.js';
import { UIController } from './ui-controller.js';
import { PageGraphRenderer } from './page-graph-renderer.js';
import { playerColorService } from './player-color-service.js';

// =============================================================================
// Main Application Class - Orchestrates all components
// =============================================================================

class WikiArenaApp {
  private taskManager: TaskManager;
  private connectionManager: TaskConnectionManager;
  private uiController: UIController;
  private pageGraphRenderer: PageGraphRenderer;
  private unsubscribeFunctions: (() => void)[] = [];

  constructor() {
    console.log('🚀 Wiki Arena Frontend initializing (task-centric architecture)...');

    // Initialize PlayerColorService first (async, but doesn't block initialization)
    this.initializeColorService();

    // Initialize components
    this.taskManager = new TaskManager();
    this.connectionManager = new TaskConnectionManager(
      (gameId, event) => this.taskManager.handleGameEvent(gameId, event)
    );
    this.uiController = new UIController();
    this.pageGraphRenderer = new PageGraphRenderer('graph-canvas');
    
    this.setupEventFlow();
    this.setupUIHandlers();

    // Ensure graph renderer has correct initial dimensions
    setTimeout(() => {
      this.pageGraphRenderer.resize();
    }, 100);

    console.log('✅ Wiki Arena Frontend ready');
  }

  private async initializeColorService(): Promise<void> {
    try {
      await playerColorService.initialize();
      console.log('🎨 PlayerColorService initialized with provider-based colors');
    } catch (error) {
      console.warn('🎨 PlayerColorService initialization failed, using fallback colors:', error);
    }
  }

  // =============================================================================
  // Event Flow Setup - Wire components together
  // =============================================================================

  private setupEventFlow(): void {
    // Connection Manager → UI Controller (task-level status)
    const unsubscribeConnectionStatus = this.connectionManager.onStatusChange(taskStatus => {
      console.log('📊 Task connection status:', taskStatus);
      
      // Convert TaskConnectionStatus to legacy ConnectionStatus format
      const legacyStatus = {
        connected: taskStatus.overallStatus === 'connected',
        connecting: taskStatus.overallStatus === 'connecting',
        error: taskStatus.errors.length > 0 ? taskStatus.errors[0] : null,
        reconnectAttempts: 0 // TODO: Aggregate from games if needed
      };
      
      this.uiController.updateConnectionStatus(legacyStatus);
    });

    // Task → Page Graph Renderer
    const unsubscribePageGraph = this.taskManager.subscribe(() => {
      const pageGraphData = this.taskManager.getVisualizationData();
      this.pageGraphRenderer.updateFromPageGraphData(pageGraphData);
    });

    // Task → UI Controller
    const unsubscribeTaskUI = this.taskManager.subscribe(task => {
      // Get stepping information from TaskManager
      const steppingInfo = {
        currentPageIndex: task.currentPageIndex,
        viewingPageIndex: task.viewingPageIndex,
        renderingMode: task.renderingMode,
        canStepForward: this.taskManager.canStepForward(),
        canStepBackward: this.taskManager.canStepBackward()
      };
      
      // Update UI with Task data directly (NEW approach)
      this.uiController.updateTask(task, steppingInfo);
      
      // Check if user selected a different game and update accordingly
      const selectedGameId = this.uiController.getSelectedGameId();
      if (selectedGameId && task.games.has(selectedGameId)) {
        // Re-render with updated selection if needed
        this.uiController.updateTask(task, steppingInfo);
      }
    });

    // Store unsubscribe functions for cleanup
    this.unsubscribeFunctions.push(
      unsubscribeConnectionStatus,
      unsubscribePageGraph,
      unsubscribeTaskUI
    );

    console.log('✅ Event flow setup complete (task-centric architecture)');
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
      // Panel starts collapsed by default
      let isCollapsed = true;
      
      // Set initial button state to match collapsed panel
      toggleButton.textContent = '📊';
      toggleButton.title = 'Show info panel';
      
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
    console.log('🎲 User requested new task with multiple games');

    // Show loading state
    this.uiController.showGameStarting();
    this.uiController.setButtonLoading('start-game-btn', true, 'Starting...');

    try {
      // Make API call to create task with multiple games
      const response = await this.createRandomTask();
      
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Task created:', data);
        
        // Extract task info from response
        const { task_id, start_page, target_page, game_ids } = data;
        
        if (!task_id || !game_ids || game_ids.length === 0) {
          throw new Error('Invalid task response: missing task_id or game_ids');
        }
        
        console.log(`🎯 Created task ${task_id} with ${game_ids.length} games: ${start_page} → ${target_page}`);
        
        // Reset task manager for new task
        this.resetTaskManager();
        
        // Create task with multiple games
        const gameConfigs = game_ids.map((gameId: string) => ({
          gameId: gameId,
          startPage: start_page,
          targetPage: target_page
        }));
        
        this.taskManager.createTask(gameConfigs);
        
        // Connect to all games in the task using connection manager
        await this.connectionManager.connectToTask(game_ids);
        
        console.log(`🔌 Connected to task ${task_id} with ${game_ids.length} games`);
      } else {
        const errorText = await response.text();
        throw new Error(`Failed to create task: ${response.status} - ${errorText}`);
      }
    } catch (error) {
      console.error('❌ Failed to start task:', error);
      this.uiController.showError(`Failed to start new task: ${error instanceof Error ? error.message : 'Unknown error'}`);
      this.uiController.updateLoadingState('Click "Start New Game" to try again');
    } finally {
      this.uiController.setButtonLoading('start-game-btn', false);
    }
  }

  public async handleStartCustomGame(startPage: string, targetPage: string): Promise<void> {
    console.log(`🎲 User requested custom task: ${startPage} -> ${targetPage}`);

    // Show loading state
    this.uiController.showGameStarting();
    this.uiController.setButtonLoading('start-game-btn', true, 'Starting...');

    try {
      // Make API call to create custom task with multiple games
      const response = await this.createCustomTask(startPage, targetPage);
      
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Custom task created:', data);
        
        // Extract task info from response
        const { task_id, start_page, target_page, game_ids } = data;
        
        if (!task_id || !game_ids || game_ids.length === 0) {
          throw new Error('Invalid task response: missing task_id or game_ids');
        }
        
        console.log(`🎯 Created custom task ${task_id} with ${game_ids.length} games: ${start_page} → ${target_page}`);
        
        // Reset task manager for new task
        this.resetTaskManager();
        
        // Create task with multiple games
        const gameConfigs = game_ids.map((gameId: string) => ({
          gameId: gameId,
          startPage: start_page,
          targetPage: target_page
        }));
        
        this.taskManager.createTask(gameConfigs);
        
        // Connect to all games in the task using connection manager
        await this.connectionManager.connectToTask(game_ids);
        
        console.log(`🔌 Connected to custom task ${task_id} with ${game_ids.length} games`);
      } else {
        const errorText = await response.text();
        throw new Error(`Failed to create custom task: ${response.status} - ${errorText}`);
      }
    } catch (error) {
      console.error('❌ Failed to start custom task:', error);
      this.uiController.showError(`Failed to start custom task: ${error instanceof Error ? error.message : 'Unknown error'}`);
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
    this.taskManager.stepBackward();
  }

  public handleStepForward(): void {
    console.log('➡️ User stepping forward');
    this.taskManager.stepForward();
  }

  public handleEnterLiveMode(): void {
    console.log('🔴 User entering live mode');
    this.taskManager.enterLiveMode();
  }

  public handleStepToMove(moveIndex: number): void {
    console.log(`🎯 User stepping to page ${moveIndex}`);
    this.taskManager.setGlobalViewingPageIndex(moveIndex);
  }

  // =============================================================================
  // Helper Methods
  // =============================================================================

  private resetTaskManager(): void {
    this.taskManager.reset();
    this.uiController.resetTaskUI(); // Updated to use new method name
  }

  // =============================================================================
  // API Calls
  // =============================================================================

  private async createCustomTask(startPage: string, targetPage: string): Promise<Response> {
    const apiUrl = 'http://localhost:8000/api/tasks';
    
    const taskRequest = {
      task_strategy: {
        type: 'custom',
        start_page: startPage,
        target_page: targetPage
      },
      model_selections: [
        {
          model_provider: 'random',
          model_name: 'random'
        },
        {
          model_provider: 'random',
          model_name: 'random'
        }
      ],
      max_steps: 30
    };
    
    return fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(taskRequest)
    });
  }

  private async createRandomTask(): Promise<Response> {
    const apiUrl = 'http://localhost:8000/api/tasks';
    
    // Create a task request with random task selection strategy and multiple games
    const taskRequest = {
      task_strategy: {
        type: 'random',
        language: 'en',
        max_retries: 3
      },
      model_selections: [
        {
          model_provider: 'random',
          model_name: 'random'
        },
        {
          model_provider: 'random',
          model_name: 'random'
        },
        // {
        //   model_provider: 'random',
        //   model_name: 'random'
        // },
      ],
      max_steps: 20
    };
    
    return fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(taskRequest)
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
    
    // Disconnect task connections
    this.connectionManager.destroy();
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
    console.log('🐛 Debug Info (Task-Centric Architecture):');
    console.log('Task Connection Status:', this.connectionManager.getTaskConnectionStatus());
    console.log('Task:', this.taskManager.getTask());
    
    // Detailed debug info
    this.taskManager.debugState();
    this.connectionManager.debugConnections();
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
      stepToMove: (moveIndex: number) => app?.handleStepToMove(moveIndex),
      // New debug methods for task-centric architecture
      debugTask: () => {
        if (app) {
          (app as any).taskManager.debugState();
        }
      },
      debugConnections: () => {
        if (app) {
          (app as any).connectionManager.debugConnections();
        }
      },
      debugColors: () => {
        playerColorService.debugState();
      },
      getPlayerColors: () => {
        return Array.from(playerColorService.getAllGameColors().entries());
      },
      simulateMultiVisit: () => {
        // Test function to simulate multi-visit nodes
        if (app) {
          console.log('🧪 Simulating multi-visit node for testing pie charts...');
          (app as any).pageGraphRenderer.debugPieCharts();
        }
      }
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

import { WikipediaAutocomplete } from './wikipedia-autocomplete.js';
import { ModelSelector, type ModelOption } from './model-selector.js';

// Basic UI functionality for the new design
class UIManager {
    private sidebar: HTMLElement;
    private landingModal: HTMLElement;
    private raceView: HTMLElement;
    private startRaceBtn: HTMLButtonElement;
    private player1Input: HTMLInputElement;
    private player2Input: HTMLInputElement;
    private player1Selector: ModelSelector | null = null;
    private player2Selector: ModelSelector | null = null;
    private startPageInput: HTMLInputElement;
    private targetPageInput: HTMLInputElement;
    private startPageAutocomplete: WikipediaAutocomplete | null = null;
    private targetPageAutocomplete: WikipediaAutocomplete | null = null;
    private pageValidationState = { start: false, target: false };
    private modelValidationState = { player1: false, player2: false };
    private app: WikiArenaApp | null = null;

    constructor() {
        this.sidebar = document.getElementById('sidebar')!;
        this.landingModal = document.getElementById('landing-modal')!;
        this.raceView = document.getElementById('race-view')!;
        this.startRaceBtn = document.getElementById('start-race-btn') as HTMLButtonElement;
        this.player1Input = document.getElementById('player1-model') as HTMLInputElement;
        this.player2Input = document.getElementById('player2-model') as HTMLInputElement;
        this.startPageInput = document.getElementById('start-page-input') as HTMLInputElement;
        this.targetPageInput = document.getElementById('target-page-input') as HTMLInputElement;

        this.initializeSidebar();
        this.initializeLandingModal();
        this.initializeAutocomplete();
        this.initializeModelSelectors();
        this.initializeFormValidation();
    }

    // Set the app instance so we can call its methods
    setApp(app: WikiArenaApp): void {
        this.app = app;
    }

    private initializeSidebar() {
        const logoBtn = document.getElementById('sidebar-logo-btn')!;
        const closeBtn = document.getElementById('sidebar-close-btn')!;
        const configureBtn = document.getElementById('configure-race-btn')!;
        const quickstartBtn = document.getElementById('quickstart-btn')!;
        const leaderboardBtn = document.getElementById('leaderboard-btn')!;

        // Toggle sidebar with logo button (when collapsed) or close button (when expanded)
        logoBtn.addEventListener('click', () => {
            this.sidebar.classList.add('expanded');
        });

        closeBtn.addEventListener('click', () => {
            this.sidebar.classList.remove('expanded');
        });

        // Configure new race - show landing modal
        configureBtn.addEventListener('click', () => {
            this.showLandingModal();
        });

        // Quickstart - start random race
        quickstartBtn.addEventListener('click', () => {
            this.startRandomRace();
        });

        // Leaderboard
        leaderboardBtn.addEventListener('click', () => {
            console.log('Leaderboard clicked');
            // TODO: Implement leaderboard
        });
    }

    private initializeLandingModal() {
        const leaderboardBtn = document.getElementById('leaderboard-modal-btn')!;
        const aboutBtn = document.getElementById('about-modal-btn')!;
        const quickstartBtn = document.getElementById('quickstart-modal-btn')!;

        leaderboardBtn.addEventListener('click', () => {
            console.log('Leaderboard modal clicked');
            // TODO: Implement leaderboard modal
        });

        aboutBtn.addEventListener('click', () => {
            console.log('About modal clicked');
            // TODO: Implement about modal
        });

        quickstartBtn.addEventListener('click', () => {
            this.startRandomRace();
        });

        this.startRaceBtn.addEventListener('click', () => {
            this.startCustomRace();
        });
    }

    private initializeAutocomplete() {
        // Initialize start page autocomplete
        this.startPageAutocomplete = new WikipediaAutocomplete(this.startPageInput, {
            placeholder: 'Search start page...',
            onSelect: (result) => {
                console.log('Start page selected:', result.title);
                this.updateStartRaceButton();
            },
            onValidationChange: (isValid) => {
                this.pageValidationState.start = isValid;
                this.updateStartRaceButton();
            }
        });

        // Initialize target page autocomplete
        this.targetPageAutocomplete = new WikipediaAutocomplete(this.targetPageInput, {
            placeholder: 'Search target page...',
            onSelect: (result) => {
                console.log('Target page selected:', result.title);
                this.updateStartRaceButton();
            },
            onValidationChange: (isValid) => {
                this.pageValidationState.target = isValid;
                this.updateStartRaceButton();
            }
        });
    }

    private initializeModelSelectors() {
        // Initialize player 1 model selector
        this.player1Selector = new ModelSelector(this.player1Input, {
            placeholder: 'Select Player 1 model...',
            onSelect: (model) => {
                console.log('Player 1 model selected:', model.displayName);
                this.updateStartRaceButton();
            },
            onValidationChange: (isValid) => {
                this.modelValidationState.player1 = isValid;
                this.updateStartRaceButton();
            }
        });

        // Initialize player 2 model selector
        this.player2Selector = new ModelSelector(this.player2Input, {
            placeholder: 'Select Player 2 model...',
            onSelect: (model) => {
                console.log('Player 2 model selected:', model.displayName);
                this.updateStartRaceButton();
            },
            onValidationChange: (isValid) => {
                this.modelValidationState.player2 = isValid;
                this.updateStartRaceButton();
            }
        });
    }

    private initializeFormValidation() {
        // Listen for changes to update start race button state
        // Note: Model selectors handle their own change events through callbacks
        [this.startPageInput, this.targetPageInput].forEach(element => {
            element.addEventListener('input', () => {
                this.updateStartRaceButton();
            });
        });

        // Initialize the form state
        this.updateStartRaceButton();
    }

    private updateStartRaceButton() {
        // Check page validation from autocomplete
        const hasValidStartPage = this.pageValidationState.start && this.startPageInput.value.trim() !== '';
        const hasValidTargetPage = this.pageValidationState.target && this.targetPageInput.value.trim() !== '';
        
        // Check model selection
        const hasPlayer1 = this.modelValidationState.player1;
        const hasPlayer2 = this.modelValidationState.player2;
        const player1ModelId = this.player1Selector?.getValue() || '';
        const player2ModelId = this.player2Selector?.getValue() || '';
        const differentModels = player1ModelId !== player2ModelId || player1ModelId === '';
        
        // Ensure start and target pages are different
        const differentPages = this.startPageInput.value.trim() !== this.targetPageInput.value.trim() || 
                              this.startPageInput.value.trim() === '';

        const isValid = hasValidStartPage && hasValidTargetPage && hasPlayer1 && hasPlayer2 && 
                       differentModels && differentPages;
        
        this.startRaceBtn.disabled = !isValid;
    }



    private showLandingModal() {
        this.landingModal.classList.remove('hidden');
    }

    private hideLandingModal() {
        this.landingModal.classList.add('hidden');
    }

    private async startRandomRace() {
        console.log('Starting random race...');
        
        if (!this.app) {
            console.error('WikiArenaApp not initialized yet');
            return;
        }

        try {
            // Hide the landing modal first
            this.hideLandingModal();
            
            // Call the main app's method to start a random race
            await this.app.handleStartGame();
            
        } catch (error) {
            console.error('Failed to start random race:', error);
            // Show the landing modal again if there was an error
            this.showLandingModal();
        }
    }

    private async startCustomRace() {
        const startPage = this.startPageInput.value.trim();
        const targetPage = this.targetPageInput.value.trim();
        const player1Model = this.player1Selector?.getValue() || '';
        const player2Model = this.player2Selector?.getValue() || '';

        console.log('Starting custom race:', {
            startPage,
            targetPage,
            player1Model,
            player2Model
        });

        if (!this.app) {
            console.error('WikiArenaApp not initialized yet');
            return;
        }

        try {
            // Hide the landing modal first
            this.hideLandingModal();
            
            // Call the main app's method to start a custom race
            await this.app.handleStartCustomGame(startPage, targetPage);
            
        } catch (error) {
            console.error('Failed to start custom race:', error);
            // Show the landing modal again if there was an error
            this.showLandingModal();
        }
    }

    // Public methods for external access
    public showLanding() {
        this.showLandingModal();
    }

    public hideLanding() {
        this.hideLandingModal();
    }

    public destroy() {
        // Clean up autocomplete instances
        if (this.startPageAutocomplete) {
            this.startPageAutocomplete.destroy();
            this.startPageAutocomplete = null;
        }
        
        if (this.targetPageAutocomplete) {
            this.targetPageAutocomplete.destroy();
            this.targetPageAutocomplete = null;
        }

        // Clean up model selector instances
        if (this.player1Selector) {
            this.player1Selector.destroy();
            this.player1Selector = null;
        }
        
        if (this.player2Selector) {
            this.player2Selector.destroy();
            this.player2Selector = null;
        }
    }
}

// Initialize the UI when the page loads
document.addEventListener('DOMContentLoaded', () => {
    const uiManager = new UIManager();
    
    // Make it globally accessible for debugging
    (window as any).uiManager = uiManager;
    
    // Wait for the main app to initialize, then connect them
    setTimeout(() => {
        const wikiArena = (window as any).wikiArena;
        if (wikiArena && wikiArena.app) {
            uiManager.setApp(wikiArena.app);
            console.log('✅ UIManager connected to WikiArenaApp');
        } else {
            console.warn('⚠️ WikiArenaApp not found, retrying...');
            // Retry a few more times
            let retries = 0;
            const maxRetries = 10;
            const retryInterval = setInterval(() => {
                const wikiArena = (window as any).wikiArena;
                if ((wikiArena && wikiArena.app) || retries >= maxRetries) {
                    clearInterval(retryInterval);
                    if (wikiArena && wikiArena.app) {
                        uiManager.setApp(wikiArena.app);
                        console.log('✅ UIManager connected to WikiArenaApp (after retry)');
                    } else {
                        console.error('❌ Failed to connect UIManager to WikiArenaApp');
                    }
                }
                retries++;
            }, 200);
        }
    }, 100);
});