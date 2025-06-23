import { 
  Task,
  GameSequence,
  PageState,
  PageGraphData,
  PageNode,
  NavigationEdge,
  GameEvent,
  GameStartedEvent,
  GameMoveCompletedEvent,
  OptimalPathsUpdatedEvent,
  GameFinishedEvent,
  ConnectionEstablishedEvent,
} from './types.js';
import { playerColorService } from './player-color-service.js';

// =============================================================================
// Task Manager - Task-Centric Data Orchestration and Business Logic
// =============================================================================

export class TaskManager {
  private task: Task = this.createEmptyTask();
  private listeners: Set<(task: Task) => void> = new Set();

  constructor() {
    console.log('📋 TaskManager initialized with task-centric architecture');
  }

  // =============================================================================
  // Task Lifecycle Management
  // =============================================================================

  private createEmptyTask(): Task { // TODO(Hunter): why to we do this and not just init from backend response?
    return {
      startPage: '',
      targetPage: '',
      shortestPathLength: 0,
      games: new Map<string, GameSequence>(),
      renderingMode: 'live',
      viewingPageIndex: -1,
      currentPageIndex: -1
    };
  }

  createTask(gameConfigs: Array<{gameId: string, startPage: string, targetPage: string}>): Task {
    // Reset for new task
    this.task = this.createEmptyTask();
    
    // Set task-level properties from first game (all games in task have same start/target)
    if (gameConfigs.length > 0) {
      this.task.startPage = gameConfigs[0].startPage;
      this.task.targetPage = gameConfigs[0].targetPage;
    }
    
    // Assign colors to players for this task
    const gameIds = gameConfigs.map(config => config.gameId);
    playerColorService.assignColorsForTask(gameIds);
    
    // Initialize game sequences
    gameConfigs.forEach(config => {
      const gameSequence: GameSequence = {
        gameId: config.gameId,
        status: 'not_started',
        pageStates: []
      };
      this.task.games.set(config.gameId, gameSequence);
    });
    
    console.log(`📋 Created task: ${this.task.startPage} → ${this.task.targetPage} with ${gameConfigs.length} games`);
    this.notifyListeners();
    return this.task;
  }

  // =============================================================================
  // Event Processing - Route events to appropriate game sequences
  // =============================================================================

  handleGameEvent(gameId: string, event: GameEvent): void {
    console.log(`📋 TaskManager processing event: ${event.type} for game ${gameId}`);
    
    const gameSequence = this.task.games.get(gameId);
    if (!gameSequence) {
      console.warn(`⚠️ No game sequence found for gameId: ${gameId}`);
      return;
    }
    
    switch (event.type) {
      case 'connection_established':
        this.handleConnectionEstablished(gameId, event as ConnectionEstablishedEvent);
        break;
      case 'GAME_STARTED':
        this.handleGameStarted(gameId, event as GameStartedEvent);
        break;
      case 'GAME_MOVE_COMPLETED':
        this.handleMoveCompleted(gameId, event as GameMoveCompletedEvent);
        break;
      case 'OPTIMAL_PATHS_UPDATED':
        this.handleOptimalPathsUpdated(gameId, event as OptimalPathsUpdatedEvent);
        break;
      case 'GAME_FINISHED':
        this.handleGameFinished(gameId, event as GameFinishedEvent);
        break;
      default:
        console.warn('⚠️ Unknown event type:', (event as any).type);
    }
  }

  private handleConnectionEstablished(gameId: string, event: ConnectionEstablishedEvent): void {
    console.log('🔌 TaskManager: processing connection established for game', gameId);
    
    const gameSequence = this.task.games.get(gameId)!;
    const completeState = event.complete_state;
    
    if (completeState?.game) {
      const gameData = completeState.game;
      
      // Update game sequence metadata
      gameSequence.status = gameData.status === 'in_progress' ? 'in_progress' : 
                           gameData.status === 'won' ? 'finished' : 'not_started';
      
      // Set task-level properties if not already set
      if (!this.task.startPage) {
        this.task.startPage = gameData.config.start_page_title;
        this.task.targetPage = gameData.config.target_page_title;
      }
      
      // Build page states from move history
      this.buildPageStatesFromMoveHistory(gameId, gameData.move_history, gameData.config);
      
      console.log(`📋 Initialized game ${gameId} with ${gameSequence.pageStates.length} page states`);
    }
    
    // Handle solver data if present
    if (completeState?.solver) {
      this.updateOptimalPathsForPage(
        gameId,
        completeState.solver.from_page_title,
        completeState.solver.optimal_paths || [],
        completeState.solver.optimal_path_length
      );
      
      // Set task-level shortest path length
      if (completeState.solver.optimal_path_length && !this.task.shortestPathLength) {
        this.task.shortestPathLength = completeState.solver.optimal_path_length;
      }
    }
    
    this.updateTaskProgress();
    this.notifyListeners();
  }

  private handleGameStarted(gameId: string, event: GameStartedEvent): void {
    console.log('🎮 TaskManager: handling game started for game', gameId);
    
    const gameSequence = this.task.games.get(gameId)!;
    gameSequence.status = 'in_progress';
    
    // Set task-level properties if not already set
    if (!this.task.startPage) {
      this.task.startPage = event.start_page.title;
      this.task.targetPage = event.target_page.title;
    }
    
    // Create initial page state for start page
    const startPageState: PageState = {
      gameId: gameId,
      pageTitle: event.start_page.title,
      moveIndex: 0,
      optimalPaths: [],
      isStartPage: true,
      isTargetPage: event.start_page.title === event.target_page.title,
      visitedFromPage: undefined
    };
    
    gameSequence.pageStates = [startPageState];
    
    console.log(`🎮 Started game ${gameId} with start page: ${event.start_page.title}`);
    this.updateTaskProgress();
    this.notifyListeners();
  }

  private handleMoveCompleted(gameId: string, event: GameMoveCompletedEvent): void {
    console.log('👟 TaskManager: handling move completed for game', gameId);
    
    const gameSequence = this.task.games.get(gameId)!;
    const move = event.move;
    
    // Create new page state for the destination page
    const newPageState: PageState = {
      gameId: gameId,
      pageTitle: move.to_page_title,
      moveIndex: move.step,
      optimalPaths: [],
      isStartPage: false,
      isTargetPage: move.to_page_title === this.task.targetPage,
      visitedFromPage: move.from_page_title,
      distanceChange: move.distanceChange // NOTE: this is always undefined until optimal path data arrives
    };
    
    // Add the new page state
    gameSequence.pageStates.push(newPageState);
    
    console.log(`👟 Added page state for game ${gameId}: ${move.to_page_title} (step ${move.step})`);
    this.updateTaskProgress();
    this.notifyListeners();
  }

  private handleOptimalPathsUpdated(gameId: string, event: OptimalPathsUpdatedEvent): void {
    console.log('🎯 TaskManager: handling optimal paths updated for game', gameId);
    
    const fromPageTitle = event.from_page_title;
    if (!fromPageTitle) {
      console.warn('⚠️ No from_page_title in optimal paths event');
      return;
    }
    
    this.updateOptimalPathsForPage(
      gameId,
      fromPageTitle,
      event.optimal_paths || [],
      event.optimal_path_length
    );
    
    // Calculate distance changes now that we have optimal path data
    this.updateDistanceChanges(gameId);
    
    // TODO(hunter): remove this after task init event refactor
    // Set task-level shortest path length if not set
    if (event.optimal_path_length && !this.task.shortestPathLength) {
      this.task.shortestPathLength = event.optimal_path_length;
    }
    
    this.notifyListeners();
  }

  private handleGameFinished(gameId: string, _event: GameFinishedEvent): void {
    console.log('🏁 TaskManager: handling game finished for game', gameId);
    
    const gameSequence = this.task.games.get(gameId)!;
    gameSequence.status = 'finished';
    
    this.updateTaskProgress();
    this.notifyListeners();
  }

  // =============================================================================
  // Page State Management
  // =============================================================================

  // TODO(hunter): remove this after task init event refactor
  private buildPageStatesFromMoveHistory(gameId: string, moveHistory: any[], config: any): void {
    const gameSequence = this.task.games.get(gameId)!;
    gameSequence.pageStates = [];
    
    // Create start page state
    const startPageState: PageState = {
      gameId: gameId,
      pageTitle: config.start_page_title,
      moveIndex: 0,
      optimalPaths: [],
      isStartPage: true,
      isTargetPage: config.start_page_title === config.target_page_title,
      visitedFromPage: undefined
    };
    
    gameSequence.pageStates.push(startPageState);
    
    // Create page states for each move
    moveHistory.forEach(move => {
      const pageState: PageState = {
        gameId: gameId,
        pageTitle: move.to_page_title,
        moveIndex: move.step,
        optimalPaths: [],
        isStartPage: false,
        isTargetPage: move.to_page_title === config.target_page_title,
        visitedFromPage: move.from_page_title
      };
      
      gameSequence.pageStates.push(pageState);
    });
  }

  private updateOptimalPathsForPage(gameId: string, pageTitle: string, paths: string[][], pathLength?: number): void {
    const gameSequence = this.task.games.get(gameId)!;
    const pageStateIndex = gameSequence.pageStates.findIndex(
      state => state.pageTitle === pageTitle
    );
    
    if (pageStateIndex >= 0) {
      const pageState = gameSequence.pageStates[pageStateIndex];
      pageState.optimalPaths = paths;
      pageState.distanceToTarget = pathLength;
      
      console.log(`✅ Updated optimal paths for game ${gameId}, page: ${pageTitle}`);
    } else {
      console.warn(`⚠️ Could not find page state for game ${gameId}, page: ${pageTitle}`);
    }
  }

  private updateDistanceChanges(gameId: string): void {
    const gameSequence = this.task.games.get(gameId)!;
    
    for (let i = 1; i < gameSequence.pageStates.length; i++) {
      const currentState = gameSequence.pageStates[i];
      const previousState = gameSequence.pageStates[i - 1];
      
      if (currentState.distanceToTarget !== undefined && 
          previousState.distanceToTarget !== undefined) {
        currentState.distanceChange = previousState.distanceToTarget - currentState.distanceToTarget;
        console.log(`📏 Updated distance change for ${currentState.pageTitle}: ${currentState.distanceChange}`);
      }
    }
  }

  // =============================================================================
  // Task Progress Management
  // =============================================================================

  private updateTaskProgress(): void {
    // Calculate current and viewing page indices across all games
    let maxCurrentPageIndex = -1;
    
    this.task.games.forEach(gameSequence => {
      const currentIndex = gameSequence.pageStates.length - 1;
      maxCurrentPageIndex = Math.max(maxCurrentPageIndex, currentIndex);
    });
    
    this.task.currentPageIndex = maxCurrentPageIndex;
    
    // Update viewing index if in live mode
    if (this.task.renderingMode === 'live') {
      this.task.viewingPageIndex = this.task.currentPageIndex;
    }
  }

  // =============================================================================
  // State Aggregation - Build unified visualization data
  // =============================================================================

  getVisualizationData(): PageGraphData {
    if (this.task.renderingMode === 'live') {
      return this.buildLiveGraphData();
    } else {
      return this.buildSteppingGraphData(this.task.viewingPageIndex);
    }
  }

  private buildLiveGraphData(): PageGraphData {
    // Initialize with start and target pages first
    const allPages = new Map<string, PageNode>();
    const allEdges: NavigationEdge[] = [];
    
    this.initializeStartAndTargetPages(allPages);
    
    this.task.games.forEach((gameSequence, _gameId) => {
      // Process all page states for this game
      gameSequence.pageStates.forEach(pageState => {
        this.addPageStateToGraph(allPages, allEdges, pageState);
      });
      
      // Add optimal path pages from most recent optimal paths (use current viewing index for live mode)
      this.addOptimalPathsToGraph(allPages, allEdges, gameSequence, this.task.currentPageIndex);
    });
    
    return { pages: Array.from(allPages.values()), edges: allEdges };
  }

  private buildSteppingGraphData(globalPageIndex: number): PageGraphData {
    // Initialize with start and target pages first
    const allPages = new Map<string, PageNode>();
    const allEdges: NavigationEdge[] = [];
    
    this.initializeStartAndTargetPages(allPages);
    
    this.task.games.forEach((gameSequence, _gameId) => {
      const pageStatesUpToIndex = gameSequence.pageStates.slice(0, globalPageIndex + 1);
      
      // Process page states up to global index for this game
      pageStatesUpToIndex.forEach(pageState => {
        this.addPageStateToGraph(allPages, allEdges, pageState);
      });
      
      // Add optimal path pages from most recent optimal paths up to viewing index
      this.addOptimalPathsToGraph(allPages, allEdges, gameSequence, globalPageIndex);
    });
    
    return { pages: Array.from(allPages.values()), edges: allEdges };
  }

  private initializeStartAndTargetPages(allPages: Map<string, PageNode>): void {
    // Add start page with explicit type and distance information
    allPages.set(this.task.startPage, {
      pageTitle: this.task.startPage,
      type: 'start',
      distanceToTarget: this.task.shortestPathLength,
      visits: [] // will be added while adding page state to graph
    });

    // Add target page with explicit type and distance = 0
    allPages.set(this.task.targetPage, {
      pageTitle: this.task.targetPage,
      type: 'target',
      distanceToTarget: 0,
      visits: []
    });
  }

  private addPageStateToGraph(allPages: Map<string, PageNode>, allEdges: NavigationEdge[], pageState: PageState): void {
    const existingPage = allPages.get(pageState.pageTitle);
    
    if (existingPage) {
      // Add this game's visit to existing page
      existingPage.visits.push({
        gameId: pageState.gameId,
        moveIndex: pageState.moveIndex,
        distanceChange: pageState.distanceChange
      });
      
      // Update type if it's not already start/target
      if (existingPage.type !== 'start' && existingPage.type !== 'target') {
        existingPage.type = 'visited';
      }
      
      // Update distance if available
      if (pageState.distanceToTarget !== undefined) {
        existingPage.distanceToTarget = pageState.distanceToTarget;
      }
    } else {
      // Create new page node
      allPages.set(pageState.pageTitle, {
        pageTitle: pageState.pageTitle,
        type: 'visited',
        distanceToTarget: pageState.distanceToTarget,
        visits: [{
          gameId: pageState.gameId,
          moveIndex: pageState.moveIndex,
          distanceChange: pageState.distanceChange
        }]
      });
    }
    
    // Add navigation edge if this is not the start page
    if (pageState.visitedFromPage) {
      allEdges.push({
        id: `${pageState.gameId}-move-${pageState.moveIndex}`,
        sourcePageTitle: pageState.visitedFromPage,
        targetPageTitle: pageState.pageTitle,
        type: 'move',
        moveIndex: pageState.moveIndex,
        distanceChange: pageState.distanceChange
      });
    }
  }

  private addOptimalPathsToGraph(allPages: Map<string, PageNode>, allEdges: NavigationEdge[], gameSequence: GameSequence, viewingIndex?: number): void {
    // Find most recent optimal paths by iterating backwards from viewing index
    const optimalPathsToRender = this.findMostRecentOptimalPaths(gameSequence, viewingIndex);
    
    if (optimalPathsToRender.length === 0) return;
    
    const MAX_PATHS_TO_RENDER = 2;
    optimalPathsToRender.slice(0, MAX_PATHS_TO_RENDER).forEach((path: string[], pathIndex: number) => {
      // Add optimal path pages
      path.forEach((pageTitle: string, index: number) => {
        const existingPage = allPages.get(pageTitle);
        const distanceToTarget = path.length - 1 - index;
        
        if (existingPage) {
          // Update distance but don't add to visits (only visited pages go in visits)
          if (existingPage.distanceToTarget === undefined) {
            existingPage.distanceToTarget = distanceToTarget;
          }
          
          // If page hasn't been visited, mark as optimal_path type
          if (existingPage.visits.length === 0 && existingPage.type !== 'start' && existingPage.type !== 'target') {
            existingPage.type = 'optimal_path';
          }
        } else {
          // Create new optimal path page (only if not start/target - they're already initialized)
          // TODO(hunter): i am 99% sure this check is not needed since start and target will always be in allPages
          if (pageTitle !== this.task.startPage && pageTitle !== this.task.targetPage) {
            allPages.set(pageTitle, {
              pageTitle,
              type: 'optimal_path',
              distanceToTarget,
              visits: []
            });
          }
        }
      });
      
      // Add optimal path edges
      for (let i = 0; i < path.length - 1; i++) {
        allEdges.push({
          id: `${gameSequence.gameId}-optimal-${pathIndex}-${i}`,
          sourcePageTitle: path[i],
          targetPageTitle: path[i + 1],
          type: 'optimal_path'
        });
      }
    });
  }

  private findMostRecentOptimalPaths(gameSequence: GameSequence, viewingIndex?: number): string[][] {
    // Use the provided viewing index, or default to the last page state
    const maxIndex = viewingIndex !== undefined ? viewingIndex : gameSequence.pageStates.length - 1;
    
    // Iterate backwards from viewing index to find the most recent optimal paths
    for (let i = maxIndex; i >= 0; i--) {
      const pageState = gameSequence.pageStates[i];
      if (pageState && pageState.optimalPaths.length > 0) {
        console.log(`🎯 Using optimal paths from page ${i}: ${pageState.pageTitle} (max index ${maxIndex}) for game ${gameSequence.gameId}`);
        return pageState.optimalPaths;
      }
    }
    
    // No optimal paths found in any previous state
    console.log(`⚠️ No optimal paths found for game ${gameSequence.gameId} up to index ${maxIndex}`);
    return [];
  }

  // =============================================================================
  // Global Navigation Controls
  // =============================================================================

  setGlobalViewingPageIndex(pageIndex: number): void {
    if (pageIndex >= 0 && pageIndex <= this.task.currentPageIndex) {
      this.task.viewingPageIndex = pageIndex;
      this.task.renderingMode = 'stepping';
      this.notifyListeners();
    }
  }

  stepBackward(): boolean {
    if (this.task.viewingPageIndex > 0) {
      this.task.viewingPageIndex--;
      this.task.renderingMode = 'stepping';
      this.notifyListeners();
      return true;
    }
    return false;
  }

  stepForward(): boolean {
    if (this.task.viewingPageIndex < this.task.currentPageIndex) {
      this.task.viewingPageIndex++;
      this.notifyListeners();
      return true;
    }
    return false;
  }

  enterLiveMode(): void {
    this.task.viewingPageIndex = this.task.currentPageIndex;
    this.task.renderingMode = 'live';
    this.notifyListeners();
  }

  canStepBackward(): boolean {
    return this.task.viewingPageIndex > 0;
  }

  canStepForward(): boolean {
    return this.task.viewingPageIndex < this.task.currentPageIndex;
  }

  // =============================================================================
  // Public API
  // =============================================================================

  getTask(): Task {
    return { ...this.task, games: new Map(this.task.games) }; // Return copy
  }

  getCurrentPageForGame(gameId: string): string | null {
    const gameSequence = this.task.games.get(gameId);
    if (!gameSequence || gameSequence.pageStates.length === 0) return null;
    
    return gameSequence.pageStates[gameSequence.pageStates.length - 1].pageTitle;
  }

  // =============================================================================
  // Subscription Management
  // =============================================================================

  subscribe(listener: (task: Task) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notifyListeners(): void {
    const taskCopy = this.getTask();
    this.listeners.forEach(listener => {
      try {
        listener(taskCopy);
      } catch (error) {
        console.error('❌ Error in task listener:', error);
      }
    });
  }

  // =============================================================================
  // Utility Methods
  // =============================================================================

  reset(): void {
    console.log('📋 TaskManager: Resetting state for new task');
    
    // Reset player colors for new task
    playerColorService.reset();
    
    this.task = this.createEmptyTask();
    this.notifyListeners();
  }

  debugState(): void {
    console.log('🔍 Task Debug:', {
      startPage: this.task.startPage,
      targetPage: this.task.targetPage,
      shortestPathLength: this.task.shortestPathLength,
      gameCount: this.task.games.size,
      currentPageIndex: this.task.currentPageIndex,
      viewingPageIndex: this.task.viewingPageIndex,
      renderingMode: this.task.renderingMode,
      games: Array.from(this.task.games.entries()).map(([gameId, gameSequence]) => ({
        gameId,
        status: gameSequence.status,
        pageCount: gameSequence.pageStates.length
      }))
    });
  }
} 