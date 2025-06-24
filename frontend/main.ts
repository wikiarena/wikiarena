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