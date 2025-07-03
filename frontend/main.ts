// Main entry point for Wiki Arena event-driven frontend
import { TaskManager } from './task-manager.js';
import { TaskConnectionManager } from './task-connection-manager.js';
import { UIController } from './ui-controller.js';
import { PageGraphRenderer } from './page-graph-renderer.js';
import { playerColorService } from './player-color-service.js';
import { LoadingAnimation } from './loading-animation.js';
import { WikipediaRandomService } from './wikipedia-random.js';

// =============================================================================
// Main Application Class - Orchestrates all components
// =============================================================================

class WikiArenaApp {
  private taskManager: TaskManager;
  private connectionManager: TaskConnectionManager;
  private uiController: UIController;
  private pageGraphRenderer: PageGraphRenderer;
  private loadingAnimation: LoadingAnimation;
  private wikipediaRandomService: WikipediaRandomService;
  private unsubscribeFunctions: (() => void)[] = [];
  private hasReceivedFirstData: boolean = false;

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
    this.loadingAnimation = new LoadingAnimation('loading-container');
    this.wikipediaRandomService = new WikipediaRandomService();
    
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
      
      // Hide loading animation when first data arrives
      if (!this.hasReceivedFirstData && pageGraphData.pages.length > 0) {
        this.hasReceivedFirstData = true;
        this.loadingAnimation.hide();
        console.log('🎯 First graph data received, hiding loading animation');
      }
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
    console.log('🎲 User requested new random task');
    // Use unified task creation with null pages (will select random pages)
    await this.createUnifiedTask(null, null);
  }

  public async handleStartCustomGame(startPage: string | null, targetPage: string | null): Promise<void> {
    console.log(`🎲 User requested custom task: ${startPage || '(empty)'} -> ${targetPage || '(empty)'}`);
    // Use unified task creation with provided pages (will use hint text or random if empty)
    await this.createUnifiedTask(startPage, targetPage);
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
    this.hasReceivedFirstData = false;
    this.taskManager.reset();
    this.uiController.resetTaskUI(); // Updated to use new method name
  }

  // =============================================================================
  // API Calls
  // =============================================================================

  private async createCustomTask(startPage: string | null, targetPage: string | null): Promise<Response> {
    const apiUrl = 'http://localhost:8000/api/tasks';
    
    const taskRequest = {
      task_strategy: {
        type: 'custom' as const,
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



  // =============================================================================
  // Lifecycle Management
  // =============================================================================

  destroy(): void {
    console.log('🧹 Cleaning up Wiki Arena Frontend');
    
    // Cleanup loading animation
    this.loadingAnimation.destroy();
    
    // Cleanup Wikipedia random service
    this.wikipediaRandomService.stopCycling();
    this.wikipediaRandomService.stopSlotMachine();
    
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

  // =============================================================================
  // Task Creation Helpers
  // =============================================================================

  /**
   * Get current hint text from an input element (from its placeholder)
   */
  private getCurrentHintText(elementId: string): string | null {
    const element = document.getElementById(elementId) as HTMLInputElement;
    if (!element) return null;
    
    const placeholder = element.placeholder;
    // Return placeholder if it's not the default search text
    if (placeholder && 
        placeholder !== 'Search Wikipedia...' && 
        placeholder !== 'Search start page...' && 
        placeholder !== 'Search target page...' &&
        placeholder.length > 0) {
      return placeholder;
    }
    
    return null;
  }

  /**
   * Resolve page selection: use provided page, or hint text, or get random page
   */
  private async resolvePageSelection(
    providedPage: string | null, 
    inputElementId: string, 
    pageType: 'start' | 'target',
    excludePage?: string
  ): Promise<string> {
    // If user provided a page, use it
    if (providedPage && providedPage.trim()) {
      return providedPage.trim();
    }

    // Try to use current hint text
    const hintText = this.getCurrentHintText(inputElementId);
    if (hintText) {
      // Set the hint text as the actual input value for user feedback
      const element = document.getElementById(inputElementId) as HTMLInputElement;
      if (element) {
        element.value = hintText;
      }
      return hintText;
    }

    // Fall back to random page selection with validation
    if (pageType === 'start') {
      return await this.wikipediaRandomService.getRandomStartPage();
    } else {
      return await this.wikipediaRandomService.getRandomTargetPage(excludePage);
    }
  }

  /**
   * Unified task creation method used by both quickstart and custom race
   */
  public async createUnifiedTask(
    requestedStartPage: string | null, 
    requestedTargetPage: string | null,
    startPageInputId: string = 'start-page-input',
    targetPageInputId: string = 'target-page-input'
  ): Promise<void> {
    console.log('🎲 Creating unified task:', { requestedStartPage, requestedTargetPage });

    // Reset state for new game
    this.hasReceivedFirstData = false;

    // Show loading state
    this.uiController.showGameStarting();
    this.uiController.setButtonLoading('start-game-btn', true, 'Starting...');
    
    // Show loading animation
    this.loadingAnimation.show();
    this.loadingAnimation.start();
    console.log('🎬 Loading animation started');

    try {
      // Resolve both pages (with validation and fallbacks)
      console.log('🔍 Resolving page selections...');
      const startPage = await this.resolvePageSelection(
        requestedStartPage, 
        startPageInputId, 
        'start'
      );
      
      const targetPage = await this.resolvePageSelection(
        requestedTargetPage, 
        targetPageInputId, 
        'target',
        startPage  // Exclude start page from target selection
      );

      // Ensure pages are different
      if (startPage === targetPage) {
        throw new Error('Start and target pages cannot be the same. Please try again.');
      }

      console.log(`✅ Resolved pages: ${startPage} → ${targetPage}`);

      // Make API call to create custom task with the resolved pages
      const response = await this.createCustomTask(startPage, targetPage);
      
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
      console.error('❌ Failed to create task:', error);
      this.loadingAnimation.hide();
      this.uiController.showError(`Failed to create task: ${error instanceof Error ? error.message : 'Unknown error'}`);
      this.uiController.updateLoadingState('Click "Start New Game" to try again');
    } finally {
      this.uiController.setButtonLoading('start-game-btn', false);
    }
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
import { ModelSelector } from './model-selector.js';

// Basic UI functionality for the new design
class UIManager {
      private sidebar: HTMLElement;
  private landingModal: HTMLElement;
  private startRaceBtn: HTMLButtonElement;
    private player1Input: HTMLInputElement;
    private player2Input: HTMLInputElement;
    private player1Selector: ModelSelector | null = null;
    private player2Selector: ModelSelector | null = null;
    private startPageInput: HTMLInputElement;
    private targetPageInput: HTMLInputElement;
    private startPageAutocomplete: WikipediaAutocomplete | null = null;
    private targetPageAutocomplete: WikipediaAutocomplete | null = null;
    private startPageSlotBtn: HTMLButtonElement;
    private targetPageSlotBtn: HTMLButtonElement;
    private pageValidationState = { start: false, target: false };
    private modelValidationState = { player1: false, player2: false };
    private app: WikiArenaApp | null = null;

    constructor() {
            this.sidebar = document.getElementById('sidebar')!;
    this.landingModal = document.getElementById('landing-modal')!;
    this.startRaceBtn = document.getElementById('start-race-btn') as HTMLButtonElement;
        this.player1Input = document.getElementById('player1-model') as HTMLInputElement;
        this.player2Input = document.getElementById('player2-model') as HTMLInputElement;
        this.startPageInput = document.getElementById('start-page-input') as HTMLInputElement;
        this.targetPageInput = document.getElementById('target-page-input') as HTMLInputElement;
        this.startPageSlotBtn = document.getElementById('start-page-slot-btn') as HTMLButtonElement;
        this.targetPageSlotBtn = document.getElementById('target-page-slot-btn') as HTMLButtonElement;

        this.initializeSidebar();
        this.initializeLandingModal();
        this.initializeAutocomplete();
        this.initializeSlotMachineButtons();
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
    // Initialize start page autocomplete with validation for outgoing links
    this.startPageAutocomplete = new WikipediaAutocomplete(this.startPageInput, {
      placeholder: 'Search start page...',
      pageType: 'start',
      onSelect: (result) => {
        console.log('Start page selected:', result.title);
        this.updateStartRaceButton();
      },
      onValidationChange: (isValid, hasLinks) => {
        this.pageValidationState.start = isValid;
        // Show additional feedback for link validation
        if (isValid && hasLinks === false) {
          console.warn(`Start page "${this.startPageInput.value}" may not have outgoing links`);
        }
        // Defer the uniqueness check until after the autocomplete component updates its own classes
        setTimeout(() => this.updateStartRaceButton(), 0);
      },
      onSlotMachineStart: () => {
        this.startPageSlotBtn.disabled = true;
      },
      onSlotMachineEnd: () => {
        this.startPageSlotBtn.disabled = false;
        this.updateStartRaceButton();
      }
    });

    // Initialize target page autocomplete with validation for incoming links
    this.targetPageAutocomplete = new WikipediaAutocomplete(this.targetPageInput, {
      placeholder: 'Search target page...',
      pageType: 'target',
      onSelect: (result) => {
        console.log('Target page selected:', result.title);
        this.updateStartRaceButton();
      },
      onValidationChange: (isValid, hasLinks) => {
        this.pageValidationState.target = isValid;
        // Show additional feedback for link validation
        if (isValid && hasLinks === false) {
          console.warn(`Target page "${this.targetPageInput.value}" may not have incoming links`);
        }
        // Defer the uniqueness check until after the autocomplete component updates its own classes
        setTimeout(() => this.updateStartRaceButton(), 0);
      },
      onSlotMachineStart: () => {
        this.targetPageSlotBtn.disabled = true;
      },
      onSlotMachineEnd: () => {
        this.targetPageSlotBtn.disabled = false;
        this.updateStartRaceButton();
      }
    });
  }

    private initializeSlotMachineButtons() {
        // Start page slot machine button
        this.startPageSlotBtn.addEventListener('click', async () => {
            if (this.startPageAutocomplete) {
                try {
                    // Clear previous value before starting
                    this.startPageAutocomplete.setValue('');
                    await this.startPageAutocomplete.startSlotMachine();
                } catch (error) {
                    console.error('Error starting slot machine for start page:', error);
                    this.startPageSlotBtn.disabled = false;
                }
            }
        });

        // Target page slot machine button
        this.targetPageSlotBtn.addEventListener('click', async () => {
            if (this.targetPageAutocomplete) {
                try {
                    // Clear previous value before starting
                    this.targetPageAutocomplete.setValue('');
                    await this.targetPageAutocomplete.startSlotMachine();
                } catch (error) {
                    console.error('Error starting slot machine for target page:', error);
                    this.targetPageSlotBtn.disabled = false;
                }
            }
        });
    }

    private initializeModelSelectors() {
        // Initialize player 1 model selector
        this.player1Selector = new ModelSelector(this.player1Input, {
            placeholder: 'Select Player 1 model...',
            onSelect: (model) => {
                console.log('Player 1 model selected:', model.id);
                this.updateStartRaceButton();
            },
            onValidationChange: (isValid) => {
                this.modelValidationState.player1 = isValid;
                this.updateStartRaceButton();
            },
            getExcludedModels: () => {
                // Exclude player 2's selected model from player 1's options
                const player2Model = this.player2Selector?.getValue();
                return player2Model ? [player2Model] : [];
            }
        });

        // Initialize player 2 model selector
        this.player2Selector = new ModelSelector(this.player2Input, {
            placeholder: 'Select Player 2 model...',
            onSelect: (model) => {
                console.log('Player 2 model selected:', model.id);
                this.updateStartRaceButton();
            },
            onValidationChange: (isValid) => {
                this.modelValidationState.player2 = isValid;
                this.updateStartRaceButton();
            },
            getExcludedModels: () => {
                // Exclude player 1's selected model from player 2's options
                const player1Model = this.player1Selector?.getValue();
                return player1Model ? [player1Model] : [];
            }
        });

        // Link the selectors together for cross-filtering
        if (this.player1Selector && this.player2Selector) {
            this.player1Selector.linkWithOtherSelectors([this.player2Selector]);
            this.player2Selector.linkWithOtherSelectors([this.player1Selector]);
        }
    }

    private initializeFormValidation() {
        // Validation is now handled by the onValidationChange callbacks in the autocomplete components,
        // which provides debouncing and a more reliable state.

        // Trigger initial validation for empty pages (they should be valid)
        this.triggerInitialPageValidation();

        // Initialize the form state
        this.updateStartRaceButton();
    }

    private triggerInitialPageValidation() {
        // Trigger validation for both autocomplete inputs
        // This will set them as valid since empty pages are now allowed
        if (this.startPageAutocomplete) {
            setTimeout(() => {
                (this.startPageAutocomplete as any).validateCurrentSelection();
            }, 100);
        }
        
        if (this.targetPageAutocomplete) {
            setTimeout(() => {
                (this.targetPageAutocomplete as any).validateCurrentSelection();
            }, 100);
        }
    }

    private updateStartRaceButton() {
        // Check page validation from autocomplete (for page existence)
        const hasValidStartPage = this.pageValidationState.start;
        const hasValidTargetPage = this.pageValidationState.target;
        
        // Check model selection
        const hasPlayer1 = this.modelValidationState.player1;
        const hasPlayer2 = this.modelValidationState.player2;
        const player1ModelId = this.player1Selector?.getValue() || '';
        const player2ModelId = this.player2Selector?.getValue() || '';
        const differentModels = player1ModelId !== player2ModelId || player1ModelId === '';
        
        // Uniqueness validation for pages
        const startPageValue = this.startPageInput.value.trim();
        const targetPageValue = this.targetPageInput.value.trim();
        const areSameAndNotEmpty = startPageValue !== '' && startPageValue === targetPageValue;

        if (areSameAndNotEmpty) {
            // Override autocomplete's validation style if pages are the same
            this.startPageInput.classList.remove('valid');
            this.startPageInput.classList.add('invalid');
            this.targetPageInput.classList.remove('valid');
            this.targetPageInput.classList.add('invalid');
        } else {
            // If they are different, let the autocomplete component's own validation rule.
            // We need to remove our 'invalid' override if the component itself thinks the input is valid.
            if (hasValidStartPage) {
                this.startPageInput.classList.add('valid');
                this.startPageInput.classList.remove('invalid');
            }
            if (hasValidTargetPage) {
                this.targetPageInput.classList.add('valid');
                this.targetPageInput.classList.remove('invalid');
            }
        }
        
        // Final validation check for the start button
        const differentPages = !areSameAndNotEmpty;
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
      
      // Call the unified task creation method with null pages (fully random)
      await this.app.createUnifiedTask(null, null);
      
    } catch (error) {
      console.error('Failed to start random race:', error);
      // Show the landing modal again if there was an error
      this.showLandingModal();
    }
  }

      private async startCustomRace() {
    const startPageValue = this.startPageInput.value.trim();
    const targetPageValue = this.targetPageInput.value.trim();
    
    // Convert empty strings to null for the API
    const startPage = startPageValue || null;
    const targetPage = targetPageValue || null;
    
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
      
      // Call the unified task creation method with the specified start/target page input IDs
      await this.app.createUnifiedTask(startPage, targetPage, 'start-page-input', 'target-page-input');
      
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