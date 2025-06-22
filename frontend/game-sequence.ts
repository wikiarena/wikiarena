// =============================================================================
// DEPRECATED: GameSequenceManager - Replaced by TaskManager
// =============================================================================
// This file has been deprecated in favor of the new task-centric architecture.
// The GameSequenceManager has been replaced by TaskManager which handles
// multiple games within a task and supports global stepping.
//
// TODO: Remove this file once migration is complete
// =============================================================================

/*
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

// =============================================================================
// Game Sequence Manager - Page-Centric Sequential State Management
// =============================================================================

export class GameSequenceManager {
  private gameSequence: GameSequence = this.createInitialSequence();
  private listeners: Set<(sequence: GameSequence) => void> = new Set();

  constructor() {
    console.log('📊 GameSequenceManager initialized with page-centric architecture');
  }

  // =============================================================================
  // Core State Management
  // =============================================================================

  private createInitialSequence(): GameSequence {
    return {
      gameId: '',
      startPage: '',
      targetPage: '',
      status: 'not_started',
      pageStates: [],
      currentPageIndex: -1,
      viewingPageIndex: -1,
      initialOptimalDistance: null,
      renderingMode: 'live'
    };
  }

  // =============================================================================
  // Event Handlers - Transform events into page state updates
  // =============================================================================

  handleEvent(event: GameEvent): void {
    console.log(`🎯 Processing event: ${event.type}`);
    
    switch (event.type) {
      case 'connection_established':
        this.handleConnectionEstablished(event as ConnectionEstablishedEvent);
        break;
      case 'GAME_STARTED':
        this.handleGameStarted(event as GameStartedEvent);
        break;
      case 'GAME_MOVE_COMPLETED':
        this.handleMoveCompleted(event as GameMoveCompletedEvent);
        break;
      case 'OPTIMAL_PATHS_UPDATED':
        this.handleOptimalPathsUpdated(event as OptimalPathsUpdatedEvent);
        break;
      case 'GAME_FINISHED':
        this.handleGameFinished(event as GameFinishedEvent);
        break;
      default:
        console.warn('⚠️ Unknown event type:', (event as any).type);
    }
  }

  handleConnectionEstablished(event: ConnectionEstablishedEvent): void {
    console.log('🔌 Page-centric: processing connection established');
    
    const completeState = event.complete_state;
    
    if (completeState?.game) {
      const gameData = completeState.game;
      
      // Update game metadata
      this.gameSequence.gameId = gameData.game_id;
      this.gameSequence.startPage = gameData.config.start_page_title;
      this.gameSequence.targetPage = gameData.config.target_page_title;
      this.gameSequence.status = gameData.status === 'in_progress' ? 'in_progress' : 
                               gameData.status === 'won' ? 'finished' : 'not_started';
      
      // Build page states from move history
      this.buildPageStatesFromMoveHistory(gameData.move_history, gameData.config);
      
      console.log(`📊 Initialized with ${this.gameSequence.pageStates.length} page states`);
    }
    
    // Handle solver data if present
    if (completeState?.solver) {
      this.updateOptimalPathsForPage(
        completeState.solver.from_page_title,
        completeState.solver.optimal_paths || [],
        completeState.solver.optimal_path_length
      );
    }
    
    this.calculateDistanceChanges();
    this.notifyListeners();
  }

  handleGameStarted(event: GameStartedEvent): void {
    console.log('🎮 Page-centric: handling game started');
    
    // Reset for new game
    this.gameSequence = this.createInitialSequence();
    this.gameSequence.gameId = event.game_id;
    this.gameSequence.startPage = event.start_page.title;
    this.gameSequence.targetPage = event.target_page.title;
    this.gameSequence.status = 'in_progress';
    
    console.log(`🎯 Game target page set to: "${this.gameSequence.targetPage}"`);
    
    // Create initial page state for start page
    const startPageState: PageState = {
      pageTitle: event.start_page.title,
      moveIndex: 0,
      optimalPaths: [],
      isStartPage: true,
      isTargetPage: event.start_page.title === event.target_page.title,
      visitedFromPage: undefined
    };
    
    this.gameSequence.pageStates = [startPageState];
    this.gameSequence.currentPageIndex = 0;
    this.gameSequence.viewingPageIndex = 0;
    
    console.log(`🎮 Started game with start page: ${event.start_page.title}`);
    this.notifyListeners();
  }

  handleMoveCompleted(event: GameMoveCompletedEvent): void {
    console.log('👟 Page-centric: handling move completed');
    
    const move = event.move;
    
    // Debug target page comparison
    const isTargetPageCheck = move.to_page_title === this.gameSequence.targetPage;
    console.log(`🎯 Target page check: "${move.to_page_title}" === "${this.gameSequence.targetPage}" = ${isTargetPageCheck}`);
    
    // Create new page state for the destination page
    const newPageState: PageState = {
      pageTitle: move.to_page_title,
      moveIndex: move.step,
      optimalPaths: [],
      isStartPage: false,
      isTargetPage: isTargetPageCheck,
      visitedFromPage: move.from_page_title
    };
    
    // Add the new page state
    this.gameSequence.pageStates.push(newPageState);
    this.gameSequence.currentPageIndex = this.gameSequence.pageStates.length - 1;
    
    // Update viewing index if in live mode
    if (this.gameSequence.renderingMode === 'live') {
      this.gameSequence.viewingPageIndex = this.gameSequence.currentPageIndex;
    }
    
    console.log(`👟 Added page state ${this.gameSequence.currentPageIndex}: ${move.to_page_title} (isTarget: ${newPageState.isTargetPage})`);
    this.notifyListeners();
  }

  handleOptimalPathsUpdated(event: OptimalPathsUpdatedEvent): void {
    console.log('🎯 Page-centric: handling optimal paths updated');
    
    const fromPageTitle = event.from_page_title;
    if (!fromPageTitle) {
      console.warn('⚠️ No from_page_title in optimal paths event');
      return;
    }
    
    this.updateOptimalPathsForPage(
      fromPageTitle,
      event.optimal_paths || [],
      event.optimal_path_length
    );
    
    this.calculateDistanceChanges();
    this.notifyListeners();
  }

  handleGameFinished(event: GameFinishedEvent): void {
    console.log('🏁 Page-centric: handling game finished');
    
    this.gameSequence.status = 'finished';
    
    this.notifyListeners();
  }

  // =============================================================================
  // Page State Management
  // =============================================================================

  private buildPageStatesFromMoveHistory(moveHistory: any[], config: any): void {
    this.gameSequence.pageStates = [];
    
    // Create start page state
    const startPageState: PageState = {
      pageTitle: config.start_page_title,
      moveIndex: 0,
      optimalPaths: [],
      isStartPage: true,
      isTargetPage: config.start_page_title === config.target_page_title,
      visitedFromPage: undefined
    };
    
    this.gameSequence.pageStates.push(startPageState);
    
    // Create page states for each move
    moveHistory.forEach(move => {
      const pageState: PageState = {
        pageTitle: move.to_page_title,
        moveIndex: move.step,
        optimalPaths: [],
        isStartPage: false,
        isTargetPage: move.to_page_title === config.target_page_title,
        visitedFromPage: move.from_page_title
      };
      
      this.gameSequence.pageStates.push(pageState);
    });
    
    this.gameSequence.currentPageIndex = this.gameSequence.pageStates.length - 1;
    this.gameSequence.viewingPageIndex = this.gameSequence.currentPageIndex;
  }

  private updateOptimalPathsForPage(pageTitle: string, paths: string[][], pathLength?: number): void {
    const pageStateIndex = this.gameSequence.pageStates.findIndex(
      state => state.pageTitle === pageTitle
    );
    
    if (pageStateIndex >= 0) {
      const pageState = this.gameSequence.pageStates[pageStateIndex];
      pageState.optimalPaths = paths;
      pageState.distanceToTarget = pathLength;
      
      // Capture initial optimal distance if this is the start page and we don't have it yet
      if (pageState.isStartPage && this.gameSequence.initialOptimalDistance === null && pathLength !== undefined) {
        this.gameSequence.initialOptimalDistance = pathLength;
        console.log(`🎯 Set initial optimal distance: ${pathLength}`);
      }
      
      console.log(`✅ Updated optimal paths for page ${pageStateIndex}: ${pageTitle}`);
    } else {
      console.warn(`⚠️ Could not find page state for: ${pageTitle}`);
    }
  }

  private calculateDistanceChanges(): void {
    for (let i = 1; i < this.gameSequence.pageStates.length; i++) {
      const currentState = this.gameSequence.pageStates[i];
      const previousState = this.gameSequence.pageStates[i - 1];
      
      if (currentState.distanceToTarget !== undefined && 
          previousState.distanceToTarget !== undefined) {
        currentState.distanceChange = previousState.distanceToTarget - currentState.distanceToTarget;
      }
    }
  }

  // =============================================================================
  // Visualization State Generation
  // =============================================================================

  getVisualizationData(): PageGraphData {
    const viewingIndex = this.gameSequence.viewingPageIndex;
    if (viewingIndex < 0) {
      return { pages: [], edges: [] };
    }
    
    // Get page states up to viewing index
    const viewingPageStates = this.gameSequence.pageStates.slice(0, viewingIndex + 1);
    
    // Create page nodes for visited pages
    const visitedPages: PageNode[] = viewingPageStates.map((state) => ({
      pageTitle: state.pageTitle,
      type: state.isStartPage ? 'start' : 
            state.isTargetPage ? 'target' : 'visited',
      distanceToTarget: state.distanceToTarget,
      distanceChange: state.distanceChange,
    }));

    // Always include target page if it hasn't been visited yet
    const allVisitedTitles = new Set(viewingPageStates.map(s => s.pageTitle));
    const targetPageNotVisited = this.gameSequence.targetPage && 
                                 !allVisitedTitles.has(this.gameSequence.targetPage);
    
    if (targetPageNotVisited) {
      visitedPages.push({
        pageTitle: this.gameSequence.targetPage!,
        type: 'target',
        distanceToTarget: 0, // It is the target page
      });
      console.log(`🎯 Added standalone target page: ${this.gameSequence.targetPage}`);
    }
    
    // Create page nodes for optimal path pages (non-visited)
    // Now include the target page in the visited set for optimal path filtering
    const visitedPageTitles = new Set([...viewingPageStates.map(s => s.pageTitle), 
                                       ...(targetPageNotVisited ? [this.gameSequence.targetPage!] : [])]);
    
    // Find the most recent optimal paths by iterating backwards from viewing index
    const optimalPathsToRender = this.findMostRecentOptimalPaths(viewingIndex);
    
    // Calculate distances for optimal path nodes
    const optimalPathPages: PageNode[] = this.calculateOptimalPathNodes(
      optimalPathsToRender, 
      visitedPageTitles
    );
    
    // Create navigation edges for moves
    const moveEdges: NavigationEdge[] = [];
    for (let i = 1; i < viewingPageStates.length; i++) {
      const state = viewingPageStates[i];
      if (state.visitedFromPage) {
        moveEdges.push({
          id: `move-${i}`,
          sourcePageTitle: state.visitedFromPage,
          targetPageTitle: state.pageTitle,
          type: 'move',
          moveIndex: state.moveIndex,
          distanceChange: state.distanceChange
        });
      }
    }
    
    // Create edges for optimal paths
    const optimalPathEdges: NavigationEdge[] = [];
    if (optimalPathsToRender.length > 0) {
      const MAX_PATHS_TO_RENDER = 2;
      
      optimalPathsToRender.slice(0, MAX_PATHS_TO_RENDER).forEach((path: string[], pathIndex: number) => {
        for (let i = 0; i < path.length - 1; i++) {
          const sourceTitle = path[i];
          const targetTitle = path[i + 1];
          
          optimalPathEdges.push({
            id: `optimal-${pathIndex}-${i}`,
            sourcePageTitle: sourceTitle,
            targetPageTitle: targetTitle,
            type: 'optimal_path'
          });
        }
      });
    }
    
    return {
      pages: [...visitedPages, ...optimalPathPages],
      edges: [...moveEdges, ...optimalPathEdges]
    };
  }

  private findMostRecentOptimalPaths(viewingIndex: number): string[][] {
    // Iterate backwards from viewing index to find the most recent optimal paths
    for (let i = viewingIndex; i >= 0; i--) {
      const pageState = this.gameSequence.pageStates[i];
      if (pageState && pageState.optimalPaths.length > 0) {
        console.log(`🎯 Using optimal paths from page ${i}: ${pageState.pageTitle} (viewing page ${viewingIndex})`);
        return pageState.optimalPaths;
      }
    }
    
    // No optimal paths found in any previous state
    return [];
  }

  private calculateOptimalPathNodes(optimalPathsToRender: string[][], visitedPageTitles: Set<string>): PageNode[] {
    if (optimalPathsToRender.length === 0) {
      return [];
    }

    const MAX_PATHS_TO_RENDER = 2; // Limit for performance
    const pageDistances = new Map<string, number>(); // Track minimum distance for each page
    
    // Calculate distances for each page in optimal paths
    optimalPathsToRender.slice(0, MAX_PATHS_TO_RENDER).forEach((path: string[]) => {
      path.forEach((pageTitle: string, index: number) => {
        // Skip visited pages and target page (handled separately)
        if (visitedPageTitles.has(pageTitle) || pageDistances.has(pageTitle)) {
          return;
        }
        // Calculate distance to target: remaining steps in this path
        const distanceToTarget = path.length - 1 - index;
        pageDistances.set(pageTitle, distanceToTarget);
      });
    });
    
    // Create PageNode objects with calculated distances
    const optimalPathPages: PageNode[] = [];
    pageDistances.forEach((distanceToTarget, pageTitle) => {
      optimalPathPages.push({
        pageTitle,
        type: 'optimal_path',
        distanceToTarget
      });
    });
    
    console.log(`📏 Created ${optimalPathPages.length} optimal path nodes with distances`);
    return optimalPathPages;
  }



  // =============================================================================
  // Public Interface
  // =============================================================================

  getSequence(): GameSequence {
    return { ...this.gameSequence }; // Return copy to prevent mutation
  }

  getCurrentPage(): string | null {
    if (this.gameSequence.currentPageIndex >= 0) {
      return this.gameSequence.pageStates[this.gameSequence.currentPageIndex].pageTitle;
    }
    return null;
  }

  getViewingPage(): string | null {
    if (this.gameSequence.viewingPageIndex >= 0) {
      return this.gameSequence.pageStates[this.gameSequence.viewingPageIndex].pageTitle;
    }
    return null;
  }

  // =============================================================================
  // Stepping Controls
  // =============================================================================

  stepBackward(): boolean {
    if (this.gameSequence.viewingPageIndex > 0) {
      this.gameSequence.viewingPageIndex--;
      this.gameSequence.renderingMode = 'stepping';
      this.notifyListeners();
      return true;
    }
    return false;
  }

  stepForward(): boolean {
    if (this.gameSequence.viewingPageIndex < this.gameSequence.currentPageIndex) {
      this.gameSequence.viewingPageIndex++;
      this.notifyListeners();
      return true;
    }
    return false;
  }

  goToPageIndex(pageIndex: number): boolean {
    if (pageIndex >= 0 && pageIndex <= this.gameSequence.currentPageIndex) {
      this.gameSequence.viewingPageIndex = pageIndex;
      this.gameSequence.renderingMode = 'stepping';
      this.notifyListeners();
      return true;
    }
    return false;
  }

  enterLiveMode(): void {
    this.gameSequence.viewingPageIndex = this.gameSequence.currentPageIndex;
    this.gameSequence.renderingMode = 'live';
    this.notifyListeners();
  }

  canStepBackward(): boolean {
    return this.gameSequence.viewingPageIndex > 0;
  }

  canStepForward(): boolean {
    return this.gameSequence.viewingPageIndex < this.gameSequence.currentPageIndex;
  }

  // =============================================================================
  // Subscription Management
  // =============================================================================

  subscribe(listener: (sequence: GameSequence) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notifyListeners(): void {
    const sequenceCopy = { ...this.gameSequence };
    this.listeners.forEach(listener => {
      try {
        listener(sequenceCopy);
      } catch (error) {
        console.error('❌ Error in game sequence listener:', error);
      }
    });
  }

  // =============================================================================
  // Utility Methods
  // =============================================================================

  reset(): void {
    this.gameSequence = this.createInitialSequence();
    this.notifyListeners();
  }

  debugState(): void {
    console.log('🔍 Game Sequence Debug:', {
      gameId: this.gameSequence.gameId,
      status: this.gameSequence.status,
      pageCount: this.gameSequence.pageStates.length,
      currentPageIndex: this.gameSequence.currentPageIndex,
      viewingPageIndex: this.gameSequence.viewingPageIndex,
      renderingMode: this.gameSequence.renderingMode,
      pageStates: this.gameSequence.pageStates.map((state, index) => ({
        index,
        page: state.pageTitle,
        moveIndex: state.moveIndex,
        distanceToTarget: state.distanceToTarget,
        hasOptimalPaths: state.optimalPaths.length > 0
      }))
    });
  }
}
*/ 