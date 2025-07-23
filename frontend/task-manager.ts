import { 
  Task,
  GameSequence,
  GameResult,
  PageState,
  PageGraphData,
  PageNode,
  NavigationEdge,
  GameEvent,
  GameMoveCompletedEvent,
  OptimalPathsUpdatedEvent,
  GameEndedEvent,
  TaskEndedEvent,
  ConnectionEstablishedEvent,
  Player,
} from './types.js';
import { ModelInfo } from './model-service.js';
import { getPlayerColor } from './player-colors.js';

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
      shortestPathLength: undefined,
      players: [],
      renderingMode: 'live',
      viewingPageIndex: -1,
      currentPageIndex: -1
    };
  }
  
  createTask(gamesInfo: Array<{ game_id: string; model: ModelInfo }>, startPage: string, targetPage: string): Task {
    // Reset for new task
    this.task = this.createEmptyTask();

    this.task.startPage = startPage;
    this.task.targetPage = targetPage;
    
    // Initialize players
    this.task.players = gamesInfo.map((info, index) => {
      const player: Player = {
        playerIndex: index,
        color: getPlayerColor(index),
        gameId: info.game_id,
        model: info.model,
        gameSequence: {
          gameId: info.game_id,
          status: 'not_started',
          pageStates: []
        },
        gameResult: undefined
      };
      return player;
    });
    
    console.log(`📋 Created task: ${this.task.startPage} → ${this.task.targetPage} with ${this.task.players.length} players`);
    this.notifyListeners();
    return this.task;
  }

  // =============================================================================
  // Event Processing - Route events to appropriate game sequences
  // =============================================================================

  handleGameEvent(gameId: string, event: GameEvent): void {
    console.log(`📋 TaskManager processing event: ${event.type} for game ${gameId}`);
    
    const player = this.task.players.find(p => p.gameId === gameId);
    if (!player) {
      console.warn(`⚠️ No player found for gameId: ${gameId}`);
      return;
    }
    
    switch (event.type) {
      case 'CONNECTION_ESTABLISHED':
        this.handleConnectionEstablished(player, event as ConnectionEstablishedEvent);
        break;
      case 'GAME_MOVE_COMPLETED':
        this.handleMoveCompleted(player, event as GameMoveCompletedEvent);
        break;
      case 'OPTIMAL_PATHS_UPDATED':
        this.handleOptimalPathsUpdated(player, event as OptimalPathsUpdatedEvent);
        break;
      case 'GAME_ENDED':
        this.handleGameEnded(player, event as GameEndedEvent);
        break;
      case 'TASK_ENDED':
        this.handleTaskEnded(event as TaskEndedEvent);
        break;
      default:
        console.warn('⚠️ Unknown event type:', (event as any).type);
    }
  }

  private handleConnectionEstablished(player: Player, event: ConnectionEstablishedEvent): void {
    console.log('🔌 TaskManager: processing connection established for game', player.gameId);
    
    const gameSequence = player.gameSequence;
    const completeState = event.complete_state;
    
    // First, process solver data to get shortest path length for task
    if (completeState?.solver_results && completeState.solver_results.length > 0) {
      console.log(`📋 Processing ${completeState.solver_results.length} solver results for game ${player.gameId}`);
      
      completeState.solver_results.forEach(solverResult => {
        // Set task-level properties if not already set
        if (!this.task.startPage && solverResult.from_page_title) {
          // We can infer start/target from solver results if game data is missing
          this.task.startPage = solverResult.from_page_title;
          this.task.targetPage = solverResult.to_page_title;
        }
        
        // Set task-level shortest path length from start page
        if (solverResult.optimal_path_length && 
            solverResult.from_page_title === (this.task.startPage || (completeState?.game?.config?.start_page_title)) &&
            !this.task.shortestPathLength) {
          this.task.shortestPathLength = solverResult.optimal_path_length;
        }
      });
    }
    
    if (completeState?.game) {
      const gameData = completeState.game;
      
      // Update game sequence metadata
      gameSequence.status = gameData.status;
      
      // Set task-level properties if not already set (fallback to game data)
      if (!this.task.startPage) {
        this.task.startPage = gameData.config.start_page_title;
        this.task.targetPage = gameData.config.target_page_title;
      }
      
      // Build page states from move history (now with shortest path length available)
      this.buildPageStatesFromMoveHistory(player, gameData.moves, gameData.config);
      
      console.log(`📋 Initialized game ${player.gameId} with ${gameSequence.pageStates.length} page states`);
    }
    
    // Update optimal paths for all pages (now that page states exist)
    if (completeState?.solver_results && completeState.solver_results.length > 0) {
      completeState.solver_results.forEach(solverResult => {
        this.updateOptimalPathsForPage(
          player,
          solverResult.from_page_title,
          solverResult.optimal_paths || [],
          solverResult.optimal_path_length
        );
      });
      
      // After updating all solver results, calculate distance changes
      this.updateDistanceChanges(player);
    }
    
    this.updateTaskProgress();
    this.notifyListeners();
  }

  private handleMoveCompleted(player: Player, event: GameMoveCompletedEvent): void {
    console.log('👟 TaskManager: handling move completed for game', player.gameId);
    
    const gameSequence = player.gameSequence;
    gameSequence.status = event.status;
    const move = event.move;
    
    // Create new page state for the destination page
    const newPageState: PageState = {
      gameId: player.gameId,
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
    
    console.log(`👟 Added page state for game ${player.gameId}: ${move.to_page_title} (step ${move.step})`);
    this.updateTaskProgress();
    this.notifyListeners();
  }

  private handleOptimalPathsUpdated(player: Player, event: OptimalPathsUpdatedEvent): void {
    console.log('🎯 TaskManager: handling optimal paths updated for game', player.gameId);
    
    const fromPageTitle = event.from_page_title;
    if (!fromPageTitle) {
      console.warn('⚠️ No from_page_title in optimal paths event');
      return;
    }
    
    this.updateOptimalPathsForPage(
      player,
      fromPageTitle,
      event.optimal_paths || [],
      event.optimal_path_length
    );
    
    // Calculate distance changes now that we have optimal path data
    this.updateDistanceChanges(player);
    
    // Set task-level shortest path length if not set
    if (event.optimal_path_length && !this.task.shortestPathLength) {
      this.task.shortestPathLength = event.optimal_path_length;
    }
    
    this.notifyListeners();
  }

  // TODO(hunter): when should we close websocket connection? (after all solves, or when next game starts?)
  private handleGameEnded(player: Player, event: GameEndedEvent): void {
    console.log('🏁 TaskManager: handling game finished for game', player.gameId);
    console.log(`💾 Status: ${event.game_result.status} (${event.game_result.steps} steps)`);
    
    // Update game sequence status
    player.gameSequence.status = event.game_result.status;
    
    // Store complete game result data
    const gameResult: GameResult = {
      gameId: event.game_result.game_id,
      modelId: event.game_result.model_id,
      config: {
        startPageTitle: event.game_result.config.start_page_title,
        targetPageTitle: event.game_result.config.target_page_title,
        maxSteps: event.game_result.config.max_steps,
        systemPromptTemplate: event.game_result.config.system_prompt_template,
      },
      status: event.game_result.status,
      steps: event.game_result.steps,
      errorMessage: event.game_result.error_message,
      totalEstimatedCostUsd: event.game_result.total_estimated_cost_usd,
      totalApiTimeMs: event.game_result.total_api_time_ms,
      averageResponseTimeMs: event.game_result.average_response_time_ms,
      apiCallCount: event.game_result.api_call_count,
      totalInputTokens: event.game_result.total_input_tokens,
      totalOutputTokens: event.game_result.total_output_tokens,
      totalTokens: event.game_result.total_tokens,
      startTimestamp: event.game_result.start_timestamp,
      endTimestamp: event.game_result.end_timestamp,
    };
    
    player.gameResult = gameResult;
    
    // Check if task is complete (all games finished)
    if (this.isTaskComplete()) {
      console.log('🎉 Task completed! All games finished - race result popup should show');
    }
    
    this.updateTaskProgress();
    this.notifyListeners();
  }

  private handleTaskEnded(event: TaskEndedEvent): void {
    console.log('🏁 TaskManager: handling task ended');
    
    // Task completion is now handled in handleGameEnded when we detect all games are done
    // This event might be redundant, but we keep it for completeness
  }

  // =============================================================================
  // Page State Management
  // =============================================================================

  private buildPageStatesFromMoveHistory(player: Player, moveHistory: any[], config: any): void {
    const gameSequence = player.gameSequence;
    gameSequence.pageStates = [];
    
    // Create start page state
    const startPageState: PageState = {
      gameId: player.gameId,
      pageTitle: config.start_page_title,
      moveIndex: 0,
      optimalPaths: [],
      isStartPage: true,
      isTargetPage: config.start_page_title === config.target_page_title,
      visitedFromPage: undefined,
      // Set distance for start page if we have task-level information
      distanceToTarget: this.task.shortestPathLength
    };
    
    gameSequence.pageStates.push(startPageState);
    
    // Create page states for each move
    moveHistory.forEach(move => {
      const pageState: PageState = {
        gameId: player.gameId,
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

  private updateOptimalPathsForPage(player: Player, pageTitle: string, paths: string[][], pathLength?: number): void {
    const gameSequence = player.gameSequence;
    
    // Find ALL page states with this title (page might be visited multiple times)
    const matchingIndices: number[] = [];
    gameSequence.pageStates.forEach((state, index) => {
      if (state.pageTitle === pageTitle) {
        matchingIndices.push(index);
      }
    });
    
    if (matchingIndices.length > 0) {
      // Update optimal paths for ALL occurrences of this page
      matchingIndices.forEach(index => {
        const pageState = gameSequence.pageStates[index];
        pageState.optimalPaths = paths;
        pageState.distanceToTarget = pathLength;
      });
      
      console.log(`✅ Updated optimal paths for game ${player.gameId}, page: ${pageTitle} (${paths.length} paths, distance: ${pathLength}) - updated ${matchingIndices.length} occurrences`);
    } else {
      console.warn(`⚠️ Could not find page state for game ${player.gameId}, page: ${pageTitle}. Available pages: ${gameSequence.pageStates.map(s => s.pageTitle).join(', ')}`);
    }
  }

  private updateDistanceChanges(player: Player): void {
    const gameSequence = player.gameSequence;
    
    for (let i = 1; i < gameSequence.pageStates.length; i++) {
      const currentState = gameSequence.pageStates[i];
      const previousState = gameSequence.pageStates[i - 1];
      
      if (currentState.distanceToTarget !== undefined && 
          previousState.distanceToTarget !== undefined) {
        currentState.distanceChange = previousState.distanceToTarget - currentState.distanceToTarget;
        // console.log(`📏 Updated distance change for ${currentState.pageTitle}: ${currentState.distanceChange}`);
      }
    }
  }



  // =============================================================================
  // Task Progress Management
  // =============================================================================

  private updateTaskProgress(): void {
    // Calculate current and viewing page indices across all games
    let maxCurrentPageIndex = -1;
    
    this.task.players.forEach(player => {
      const currentIndex = player.gameSequence.pageStates.length - 1;
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
    
    this.task.players.forEach(player => {
      // Process all page states for this game
      player.gameSequence.pageStates.forEach(pageState => {
        this.addPageStateToGraph(allPages, allEdges, pageState);
      });
      
      // Add optimal path pages from most recent optimal paths (use current viewing index for live mode)
      // this.addOptimalPathsToGraph(allPages, allEdges, player.gameSequence, this.task.currentPageIndex);
    });
    
    const colorMap = new Map(this.task.players.map(p => [p.gameId, p.color]));
    const spawnDirectionMap = new Map(this.task.players.map(p => 
        [p.gameId, p.playerIndex % 2 === 0 ? 'counter-clockwise' : 'clockwise'] as const
    ));
    
    return { pages: Array.from(allPages.values()), edges: allEdges, colorMap, spawnDirectionMap };
  }

  private buildSteppingGraphData(globalPageIndex: number): PageGraphData {
    // Initialize with start and target pages first
    const allPages = new Map<string, PageNode>();
    const allEdges: NavigationEdge[] = [];
    
    this.initializeStartAndTargetPages(allPages);
    
    this.task.players.forEach(player => {
      const pageStatesUpToIndex = player.gameSequence.pageStates.slice(0, globalPageIndex + 1);
      
      // Process page states up to global index for this game
      pageStatesUpToIndex.forEach(pageState => {
        this.addPageStateToGraph(allPages, allEdges, pageState);
      });
      
      // Add optimal path pages from most recent optimal paths up to viewing index
      // this.addOptimalPathsToGraph(allPages, allEdges, player.gameSequence, globalPageIndex);
    });
    
    const colorMap = new Map(this.task.players.map(p => [p.gameId, p.color]));
    const spawnDirectionMap = new Map(this.task.players.map(p =>
        [p.gameId, p.playerIndex % 2 === 0 ? 'counter-clockwise' : 'clockwise'] as const
    ));
    
    return { pages: Array.from(allPages.values()), edges: allEdges, colorMap, spawnDirectionMap };
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
      
      // Update distance if available (unlikely)
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

  // private addOptimalPathsFromEachPage(allPages: Map<string, PageNode>, allEdges: NavigationEdge[], gameSequence: GameSequence, viewingIndex?: number): void {
  //   // Use the provided viewing index, or default to the last page state
  //   const maxIndex = viewingIndex !== undefined ? viewingIndex : gameSequence.pageStates.length - 1;
    
  //   // Iterate through each page state up to the viewing index
  //   for (let i = 0; i <= maxIndex; i++) {
  //     const pageState = gameSequence.pageStates[i];
  //     if (pageState && pageState.optimalPaths.length > 0) {
  //       // Take only the first optimal path from this page
  //       const optimalPath = pageState.optimalPaths[0];
        
  //       console.log(`🎯 Adding optimal path from page ${i}: ${pageState.pageTitle} for game ${gameSequence.gameId}`);
        
  //       // Add optimal path pages
  //       optimalPath.forEach((pageTitle: string, index: number) => {
  //         const existingPage = allPages.get(pageTitle);
  //         const distanceToTarget = optimalPath.length - 1 - index;
          
  //         if (existingPage) {
  //           // Update distance but don't add to visits (only visited pages go in visits)
  //           if (existingPage.distanceToTarget === undefined) {
  //             existingPage.distanceToTarget = distanceToTarget;
  //           }
            
  //           // If page hasn't been visited, mark as optimal_path type
  //           if (existingPage.visits.length === 0 && existingPage.type !== 'start' && existingPage.type !== 'target') {
  //             existingPage.type = 'optimal_path';
  //           }
  //         } else {
  //           // Create new optimal path page (only if not start/target - they're already initialized)
  //           if (pageTitle !== this.task.startPage && pageTitle !== this.task.targetPage) {
  //             allPages.set(pageTitle, {
  //               pageTitle,
  //               type: 'optimal_path',
  //               distanceToTarget,
  //               visits: []
  //             });
  //           }
  //         }
  //       });
        
  //       // Add optimal path edges
  //       for (let j = 0; j < optimalPath.length - 1; j++) {
  //         allEdges.push({
  //           id: `${gameSequence.gameId}-optimal-page${i}-${j}`,
  //           sourcePageTitle: optimalPath[j],
  //           targetPageTitle: optimalPath[j + 1],
  //           type: 'optimal_path'
  //         });
  //       }
  //     }
  //   }
  // }

  private addOptimalPathsToGraph(allPages: Map<string, PageNode>, allEdges: NavigationEdge[], gameSequence: GameSequence, viewingIndex?: number): void {
    // Find most recent optimal paths by iterating backwards from viewing index
    const optimalPathsToRender = this.findMostRecentOptimalPaths(gameSequence, viewingIndex);
    
    if (optimalPathsToRender.length === 0) return;
    
    const MAX_PATHS_TO_RENDER = 1;
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
          // if (pageTitle !== this.task.startPage && pageTitle !== this.task.targetPage) {
            allPages.set(pageTitle, {
              pageTitle,
              type: 'optimal_path',
              distanceToTarget,
              visits: []
            });
          // }
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
    return { ...this.task, players: [...this.task.players] }; // Return copy
  }

  getCurrentPageForGame(gameId: string): string | null {
    const player = this.task.players.find(p => p.gameId === gameId);
    if (!player || player.gameSequence.pageStates.length === 0) return null;
    
    return player.gameSequence.pageStates[player.gameSequence.pageStates.length - 1].pageTitle;
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
    
    this.task = this.createEmptyTask();
    this.notifyListeners();
  }

  debugState(): void {
    console.log('🔍 Task Debug:', {
      startPage: this.task.startPage,
      targetPage: this.task.targetPage,
      shortestPathLength: this.task.shortestPathLength,
      playerCount: this.task.players.length,
      currentPageIndex: this.task.currentPageIndex,
      viewingPageIndex: this.task.viewingPageIndex,
      renderingMode: this.task.renderingMode,
      players: this.task.players.map(player => ({
        gameId: player.gameId,
        modelId: player.model.id,
        status: player.gameSequence.status,
        pageCount: player.gameSequence.pageStates.length
      }))
    });
  }

  private isTaskComplete(): boolean {
    // Need at least one game to be considered for completion
    if (this.task.players.length === 0) return false;
    
    // Check if all games have results (meaning they've finished)
    return this.task.players.every(p => p.gameResult);
    
    // Double-check that all game sequences have finished status
    // Updated to include actual status values from backend
    // const notFinishedStatuses = ['not_started', 'in_progress'];
    // for (const [_gameId, gameSequence] of this.task.games) {
    //   if (notFinishedStatuses.includes(gameSequence.status)) {
    //     return false;
    //   }
    // }
    
    return true;
  }

  // Public method to check if task is complete (for UI components)
  isCurrentTaskComplete(): boolean {
    return this.isTaskComplete();
  }
} 