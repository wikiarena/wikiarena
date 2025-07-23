// Main entry point for Wiki Arena event-driven frontend
import { TaskManager } from './task-manager.js';
import { TaskConnectionManager } from './task-connection-manager.js';
import { RaceHUDController } from './race-hud-controller.js';
import { PageGraphRenderer } from './page-graph-renderer.js';
import { LoadingAnimation } from './loading-animation.js';
import { type ModelInfo } from './model-selector.js';
import { WikipediaStatsService } from './wikipedia-stats.js';

// =============================================================================
// Main Application Class - Orchestrates all components
// =============================================================================

class WikiArenaApp {
  private taskManager: TaskManager;
  private connectionManager: TaskConnectionManager;
  private raceHUDController: RaceHUDController;
  private pageGraphRenderer: PageGraphRenderer;
  private loadingAnimation: LoadingAnimation;
  private unsubscribeFunctions: (() => void)[] = [];
  private hasReceivedFirstData: boolean = false;

  constructor() {
    console.log('🚀 Wiki Arena Frontend initializing (task-centric architecture)...');

    // Initialize components
    this.taskManager = new TaskManager();
    this.connectionManager = new TaskConnectionManager(
      (gameId, event) => this.taskManager.handleGameEvent(gameId, event)
    );
    this.raceHUDController = new RaceHUDController();
    this.pageGraphRenderer = new PageGraphRenderer('graph-canvas');
    this.loadingAnimation = new LoadingAnimation('loading-container', 200, 300, 6, 300);
    
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
      
      // Update UI with Task data directly
      this.raceHUDController.updateTask(task, steppingInfo);
    });

    // Store unsubscribe functions for cleanup
    this.unsubscribeFunctions.push(
      unsubscribePageGraph,
      unsubscribeTaskUI
    );

    console.log('✅ Event flow setup complete (task-centric architecture)');
  }

  // =============================================================================
  // UI Event Handlers - Bridge between UI and business logic
  // =============================================================================

  private setupUIHandlers(): void {
    // Set up race HUD event handlers
    this.raceHUDController.setupEventListeners({
      onStepToMove: (moveIndex: number) => this.handleStepToMove(moveIndex),
      onEnterLiveMode: () => this.handleEnterLiveMode(),
      onConfigureNewRace: () => this.handleConfigureNewRace(),
      onQuickstart: () => this.handleQuickstart()
    });

    console.log('✅ UI handlers setup complete');
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
  
  public async handleStartCustomRace(startPage: string | null, targetPage: string | null, player1Model: ModelInfo | null, player2Model: ModelInfo | null): Promise<void> {
    console.log(`🎲 User requested custom task: ${startPage || '(empty)'} -> ${targetPage || '(empty)'}`);

    // Reset state for new race
    this.hasReceivedFirstData = false;

    // Show loading animation
    this.loadingAnimation.show();
    this.loadingAnimation.start();
    console.log('🎬 Loading animation started');

    try {
      // Make API call to create custom task with multiple games
      const response = await this.createCustomTask(startPage, targetPage, player1Model, player2Model);
      
      if (response.ok) {
        const data = await response.json();
        
        const { task_id, start_page, target_page, players } = data;
        
        if (!task_id || !players || players.length === 0) {
          throw new Error('Invalid task response: missing task_id or players');
        }
        
        console.log(`🎯 Created custom task ${task_id} with ${players.length} players: ${start_page} → ${target_page}`);
        
        // Reset task manager for new task
        this.resetTaskManager();
        
        // Create task with multiple players
        this.taskManager.createTask(players, start_page, target_page);
        
        // Connect to all players in the task using connection manager
        const game_ids = players.map((g: any) => g.game_id);
        await this.connectionManager.connectToTask(game_ids);
        
        console.log(`🔌 Connected to custom task ${task_id} with ${players.length} players`);
      } else {
        const errorText = await response.text();
        throw new Error(`Failed to create task: ${response.status} - ${errorText}`);
      }
    } catch (error) {
      console.error('❌ Failed to start task:', error);
      this.loadingAnimation.hide();
      // Re-throw the error to be handled by the UI layer
      throw error;
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
    console.log(`👆 User stepped to move index: ${moveIndex}`);
    this.taskManager.setGlobalViewingPageIndex(moveIndex);
  }

  // Race result popup handlers
  private handleConfigureNewRace(): void {
    console.log('🕹️ User clicked Configure New Race');
    // Use the same logic as the sidebar configure button
    const uiManager = (window as any).uiManager;
    if (uiManager) {
      uiManager.showLanding();
    } else {
      console.warn('⚠️ UIManager not found, falling back to direct modal access');
      // Fallback: show the landing modal directly
      const landingModal = document.getElementById('landing-modal');
      if (landingModal) {
        landingModal.classList.remove('hidden');
      }
    }
    
    // Reset the current task
    this.resetTaskManager();
  }

  private handleQuickstart(): void {
    console.log('🎲 User clicked Quickstart');
    // Use the same logic as the sidebar quickstart button
    const uiManager = (window as any).uiManager;
    if (uiManager) {
      uiManager.startQuickstart();
    } else {
      console.warn('⚠️ UIManager not found, falling back to direct race start');
      // Fallback: start race with null values (random selection)
      this.handleStartCustomRace(null, null, null, null).catch(error => {
        console.error('Failed to start quickstart:', error);
      });
    }
  }

  // =============================================================================
  // Helper Methods
  // =============================================================================

  private resetTaskManager(): void {
    this.hasReceivedFirstData = false;
    this.taskManager.reset();
    this.raceHUDController.resetTaskUI(); // Updated to use new method name
  }

  // =============================================================================
  // API Calls
  // =============================================================================

  private async createCustomTask(startPage: string | null, targetPage: string | null, player1Model: ModelInfo | null, player2Model: ModelInfo | null): Promise<Response> {
    const apiUrl = 'http://localhost:8000/api/tasks';
    
    const model_ids = [
        player1Model ? player1Model.id : 'wikiarena/random',
        player2Model ? player2Model.id : 'wikiarena/random'
    ];
    
    const taskRequest = {
      task_strategy: {
        type: 'custom' as const,
        start_page: startPage,
        target_page: targetPage
      },
      model_ids: model_ids,
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
    this.raceHUDController.debugElements();
    
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
      startCustomRace: (start: string, target: string) => app?.handleStartCustomRace(start, target, null, null),
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

// View state management
enum ViewState {
    LANDING = 'landing',
    ABOUT = 'about',
    LEADERBOARD = 'leaderboard',
    RACE = 'race'
}

// Basic UI functionality for the new design
class UIManager {
    private sidebar: HTMLElement;
    private landingModal: HTMLElement;
    private raceView: HTMLElement;
    private aboutPage: HTMLElement;
    private leaderboardPage: HTMLElement;
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
    private errorMessageElement: HTMLElement;
    private pageValidationState = { start: false, target: false };
    private modelValidationState = { player1: false, player2: false };
    private app: WikiArenaApp | null = null;
    private aboutLeftAnimation: LoadingAnimation | null = null;
    private aboutRightAnimation: LoadingAnimation | null = null;
    private wikipediaStatsService: WikipediaStatsService;
    
    // View state tracking
    private currentView: ViewState = ViewState.LANDING;

    constructor() {
        this.sidebar = document.getElementById('sidebar')!;
        this.landingModal = document.getElementById('landing-modal')!;
        this.raceView = document.getElementById('race-view')!;
        this.aboutPage = document.getElementById('about-page')!;
        this.leaderboardPage = document.getElementById('leaderboard-page')!;
        this.startRaceBtn = document.getElementById('start-race-btn') as HTMLButtonElement;
        this.player1Input = document.getElementById('player1-model') as HTMLInputElement;
        this.player2Input = document.getElementById('player2-model') as HTMLInputElement;
        this.startPageInput = document.getElementById('start-page-input') as HTMLInputElement;
        this.targetPageInput = document.getElementById('target-page-input') as HTMLInputElement;
        this.startPageSlotBtn = document.getElementById('start-page-slot-btn') as HTMLButtonElement;
        this.targetPageSlotBtn = document.getElementById('target-page-slot-btn') as HTMLButtonElement;
        this.errorMessageElement = document.getElementById('landing-error-message') as HTMLElement;
        this.wikipediaStatsService = new WikipediaStatsService();

        this.initializeSidebar();
        this.initializeLandingModal();
        this.initializeAboutPage();
        this.initializeLeaderboardPage();
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
            this.showLanding();
        });

        // Quickstart - start random race
        quickstartBtn.addEventListener('click', () => {
            this.startCustomRace();
        });

        // Leaderboard
        leaderboardBtn.addEventListener('click', () => {
            this.showLeaderboard();
        });

        // About
        const aboutBtn = document.getElementById('about-btn')!;
        aboutBtn.addEventListener('click', async () => {
            await this.showAbout();
        });
    }

    private initializeLandingModal() {
        const leaderboardBtn = document.getElementById('leaderboard-modal-btn')!;
        const aboutBtn = document.getElementById('about-modal-btn')!;

        leaderboardBtn.addEventListener('click', () => {
            this.showLeaderboard();
        });

        aboutBtn.addEventListener('click', async () => {
            await this.showAbout();
        });

        this.startRaceBtn.addEventListener('click', () => {
            this.startCustomRace();
        });
    }

    private initializeAboutPage() {
        // Initialize close button
        const aboutCloseBtn = document.getElementById('about-close-btn')!;
        aboutCloseBtn.addEventListener('click', () => {
            this.showLanding();
        });

        // Initialize side loading animations with slower timing
        this.aboutLeftAnimation = new LoadingAnimation('about-left-animation', 200, 600, 8, 800);
        this.aboutRightAnimation = new LoadingAnimation('about-right-animation', 200, 600, 8, 800);
    }

    private initializeLeaderboardPage() {
        const leaderboardCloseBtn = document.getElementById('leaderboard-close-btn')!;
        leaderboardCloseBtn.addEventListener('click', () => {
            this.showLanding();
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

        // Initialize target page autocomplete
        this.targetPageAutocomplete = new WikipediaAutocomplete(this.targetPageInput, {
            placeholder: 'Search target page...',
            onSelect: (result) => {
                console.log('Target page selected:', result.title);
                this.updateStartRaceButton();
            },
            onValidationChange: (isValid) => {
                this.pageValidationState.target = isValid;
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
                const player2Model = this.player2Selector?.getSelectedModel();
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
                const player1Model = this.player1Selector?.getSelectedModel();
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
        this.triggerInitialModelValidation();

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

    private triggerInitialModelValidation() {
        if (this.player1Selector) {
            setTimeout(() => {
                this.player1Selector!.validateCurrentSelection();
            }, 100);
        }

        if (this.player2Selector) {
            setTimeout(() => {
                this.player2Selector!.validateCurrentSelection();
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
        const isValid = hasValidStartPage && hasValidTargetPage && hasPlayer1 && hasPlayer2 && differentPages;
        
        this.startRaceBtn.disabled = !isValid;
    }

    // =============================================================================
    // Centralized View Management System
    // =============================================================================

    private showView(targetView: ViewState): void {
        if (this.currentView === targetView) {
            return; // Already showing target view
        }

        console.log(`👁️ View transition: ${this.currentView} → ${targetView}`);

        // Always hide all views first
        this.hideAllViews();

        // Show target view and handle specific initialization
        switch (targetView) {
            case ViewState.LANDING:
                this.landingModal.classList.remove('hidden');
                break;

            case ViewState.ABOUT:
                this.aboutPage.classList.add('visible');
                // Start side animations
                if (this.aboutLeftAnimation) {
                    this.aboutLeftAnimation.show();
                    this.aboutLeftAnimation.start();
                }
                if (this.aboutRightAnimation) {
                    this.aboutRightAnimation.show();
                    this.aboutRightAnimation.start();
                }
                break;

            case ViewState.LEADERBOARD:
                this.leaderboardPage.classList.add('visible');
                break;

            case ViewState.RACE:
                this.raceView.style.display = 'block';
                break;
        }

        this.currentView = targetView;
    }

    private hideAllViews(): void {
        // Hide landing modal
        this.landingModal.classList.add('hidden');

        // Hide about page and stop animations
        this.aboutPage.classList.remove('visible');
        if (this.aboutLeftAnimation) {
            this.aboutLeftAnimation.stop();
            this.aboutLeftAnimation.hide();
        }
        if (this.aboutRightAnimation) {
            this.aboutRightAnimation.stop();
            this.aboutRightAnimation.hide();
        }

        // Hide leaderboard page
        this.leaderboardPage.classList.remove('visible');

        // Hide race view
        this.raceView.style.display = 'none';
    }

    // =============================================================================
    // Public View Transition API
    // =============================================================================

    public showLanding(): void {
        this._clearError();
        this.clearFormInputs();
        this.showView(ViewState.LANDING);
    }

    public async showAbout(): Promise<void> {
        this.showView(ViewState.ABOUT);
        await this.updateAboutPageStats();
    }

    public showLeaderboard(): void {
        this.showView(ViewState.LEADERBOARD);
    }

    private async updateAboutPageStats(): Promise<void> {
        try {
            const stats = await this.wikipediaStatsService.getFormattedStats();
            
            // Update only the dynamic numbers, labels stay in HTML
            const articleStatNumber = document.querySelector('.about-stats .about-stat:first-child .about-stat-number');
            const taskStatNumber = document.querySelector('.about-stats .about-stat:nth-child(2) .about-stat-number');
            
            if (articleStatNumber) {
                articleStatNumber.textContent = stats.articles;
            }
            if (taskStatNumber) {
                taskStatNumber.textContent = stats.tasks;
            }
            
            console.log('About page statistics updated:', stats);
        } catch (error) {
            console.error('Failed to update about page statistics:', error);
            // Fallback to placeholder values - they're already in the HTML
        }
    }

    public showRace(): void {
        this.showView(ViewState.RACE);
    }

    private _displayError(message: string) {
        if (this.errorMessageElement) {
            this.errorMessageElement.textContent = message;
            this.errorMessageElement.style.display = 'block';
        }
    }

    private _clearError() {
        if (this.errorMessageElement) {
            this.errorMessageElement.textContent = '';
            this.errorMessageElement.style.display = 'none';
        }
    }

    private async startCustomRace() {
        const startPage = this.startPageInput.value.trim() || null;
        const targetPage = this.targetPageInput.value.trim() || null;
        
        const player1Model = this.player1Selector?.getSelectedModel() || null;
        const player2Model = this.player2Selector?.getSelectedModel() || null;

        console.log('Starting custom race:', {
            startPage,
            targetPage,
            player1Model: player1Model?.id || 'wikiarena/random',
            player2Model: player2Model?.id || 'wikiarena/random'
        });

        if (!this.app) {
            console.error('WikiArenaApp not initialized yet');
            return;
        }

        try {
            // At the start of the action, clear old errors and show race view.
            this._clearError();
            this.showRace();
            
            // Call the main app's method to start a custom race
            await this.app.handleStartCustomRace(startPage, targetPage, player1Model, player2Model);
            
        } catch (error) {
            console.error('Failed to start custom race:', error);
            
            const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred.';
            
            // Extract details from FastAPI's HTTP Exception if possible
            let finalMessage = errorMessage;
            // Example message: "Failed to create task: 422 - {"detail":"Invalid Page: Page 'NonExistentPage' not found."}"
            if (errorMessage.includes("Failed to create task")) {
                try {
                    const jsonString = errorMessage.substring(errorMessage.indexOf('{'));
                    const errorJson = JSON.parse(jsonString);
                    if (errorJson.detail) {
                        finalMessage = errorJson.detail;
                    }
                } catch (e) {
                    // Ignore parsing error, use original message.
                }
            }
            
            // On failure, show the landing modal again and display the new error.
            this.showLanding();
            this._displayError(finalMessage);
        }
    }

    // Legacy method - now handled by centralized view system
    public hideLanding() {
        // This method is kept for backwards compatibility but shouldn't be needed
        this.showLanding();
    }

    private clearFormInputs() {
        // Clear all form inputs: Wikipedia autocomplete and model selectors
        if (this.startPageAutocomplete) {
            this.startPageAutocomplete.clear();
        }
        
        if (this.targetPageAutocomplete) {
            this.targetPageAutocomplete.clear();
        }
        
        // Clear the model selector inputs
        if (this.player1Selector) {
            this.player1Selector.clear();
        }
        
        if (this.player2Selector) {
            this.player2Selector.clear();
        }
    }

    public startQuickstart() {
        // Start a quickstart with random pages and models (bypassing form validation)
        if (!this.app) {
            console.error('WikiArenaApp not initialized yet');
            return;
        }

        console.log('Starting quickstart with random selection...');
        
        try {
            // Clear old errors and show race view
            this._clearError();
            this.showRace();
            
            // Start race with null values for random selection
            this.app.handleStartCustomRace(null, null, null, null);
            
        } catch (error) {
            console.error('Failed to start quickstart:', error);
            
            const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred.';
            
            // On failure, show the landing modal again and display the error
            this.showLanding();
            this._displayError(errorMessage);
        }
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

        // Clean up about page animations
        if (this.aboutLeftAnimation) {
            this.aboutLeftAnimation.destroy();
            this.aboutLeftAnimation = null;
        }
        
        if (this.aboutRightAnimation) {
            this.aboutRightAnimation.destroy();
            this.aboutRightAnimation = null;
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