import { 
  GameState, 
  GameEvent, 
  GameStartedEvent, 
  GameMoveCompletedEvent, 
  OptimalPathsUpdatedEvent, 
  GameFinishedEvent,
  ConnectionEstablishedEvent,
  Move 
} from './types.js';

// =============================================================================
// Game State Manager - Single source of truth for game data
// =============================================================================

export class GameStateManager {
  private state: GameState;
  private listeners: Set<(state: GameState) => void> = new Set();

  constructor() {
    this.state = this.createInitialState();
  }

  // =============================================================================
  // State Initialization
  // =============================================================================

  private createInitialState(): GameState {
    return {
      gameId: null,
      status: 'not_started',
      startPage: null,
      targetPage: null,
      currentPage: null,
      moves: [],
      optimalPaths: [],
      currentOptimalDistance: null,
      totalMoves: 0,
      success: null
    };
  }

  // =============================================================================
  // Event Handlers - Transform events into state updates
  // =============================================================================

  handleConnectionEstablished(event: ConnectionEstablishedEvent): void {
    console.log('🔌 WebSocket connected, processing complete state');
    
    const completeState = event.complete_state;
    
    if (completeState?.game) {
      // Set game state from complete state
      const gameData = completeState.game;
      const newState: GameState = {
        ...this.state,
        gameId: gameData.game_id,
        status: gameData.status === 'in_progress' ? 'in_progress' : 
                gameData.status === 'won' ? 'finished' : 'not_started',
        startPage: gameData.config.start_page_title,
        targetPage: gameData.config.target_page_title,
        currentPage: gameData.current_page?.title || gameData.config.start_page_title,
        moves: gameData.move_history.map(move => ({
          from_page_title: move.from_page_title,
          to_page_title: move.to_page_title,
          step: move.step
        })),
        totalMoves: gameData.steps,
        success: gameData.status === 'won'
      };
      
      this.updateState(newState);
    }
    
    if (completeState?.solver) {
      // Set solver results from complete state
      const solverData = completeState.solver;
      const currentState = this.getState();
      
      const enhancedState: GameState = {
        ...currentState,
        optimalPaths: solverData.optimal_paths || [],
        currentOptimalDistance: solverData.optimal_path_length
      };
      
      this.updateState(enhancedState);
    }
    
    if (!completeState?.game && !completeState?.solver) {
      console.log('🔌 WebSocket connected to game (no state available yet)');
    }
  }

  handleGameStarted(event: GameStartedEvent): void {
    console.log('🎮 Game state: handling game started');
    
    const newState: GameState = {
      ...this.state,
      gameId: event.game_id,
      status: 'in_progress',
      startPage: event.start_page.title,
      targetPage: event.target_page.title,
      currentPage: event.start_page.title,
      moves: [],
      optimalPaths: [],
      currentOptimalDistance: null,
      totalMoves: 0,
      success: null
    };

    this.updateState(newState);
  }

  handleMoveCompleted(event: GameMoveCompletedEvent): void {
    console.log('👟 Game state: handling move completed');
    
    const move = event.move;
    const currentPage = event.current_page.title;

    // Add move to history (keep moves sorted by step)
    const newMoves = [...this.state.moves, move].sort((a, b) => a.step - b.step);

    const newState: GameState = {
      ...this.state,
      currentPage,
      moves: newMoves,
      totalMoves: newMoves.length
    };

    this.updateState(newState);
  }

  handleOptimalPathsUpdated(event: OptimalPathsUpdatedEvent): void {
    console.log('🎯 Game state: handling optimal paths updated');
    
    const newState: GameState = {
      ...this.state,
      // Handle backend sending optimal_paths as array or empty
      optimalPaths: Array.isArray(event.optimal_paths) ? event.optimal_paths : [],
      currentOptimalDistance: event.optimal_path_length || null
    };

    this.updateState(newState);
  }

  handleGameFinished(event: GameFinishedEvent): void {
    console.log('🏁 Game state: handling game finished');
    
    const newState: GameState = {
      ...this.state,
      status: 'finished',
      success: event.success,
      totalMoves: event.total_moves
    };

    this.updateState(newState);
  }

  // =============================================================================
  // State Management
  // =============================================================================

  private updateState(newState: GameState): void {
    this.state = newState;

    console.log('📊 State updated:', {
      gameId: newState.gameId,
      status: newState.status,
      currentPage: newState.currentPage,
      totalMoves: newState.totalMoves,
      optimalDistance: newState.currentOptimalDistance
    });

    // Notify all listeners
    this.notifyListeners();
  }

  private notifyListeners(): void {
    this.listeners.forEach(listener => {
      try {
        listener(this.state);
      } catch (error) {
        console.error('❌ Error in state listener:', error);
      }
    });
  }

  // =============================================================================
  // Public API
  // =============================================================================

  getState(): GameState {
    return { ...this.state }; // Return copy to prevent mutations
  }

  subscribe(listener: (state: GameState) => void): () => void {
    this.listeners.add(listener);
    
    // Immediately call with current state
    listener(this.state);
    
    // Return unsubscribe function
    return () => {
      this.listeners.delete(listener);
    };
  }

  // Reset state (useful for starting new games)
  reset(): void {
    console.log('🔄 Resetting game state');
    this.updateState(this.createInitialState());
  }

  // Set state directly (for demo purposes)
  setState(newState: GameState): void {
    console.log('🎭 Setting demo state');
    this.updateState(newState);
  }

  // =============================================================================
  // Convenience Getters
  // =============================================================================

  isGameActive(): boolean {
    return this.state.status === 'in_progress';
  }

  isGameFinished(): boolean {
    return this.state.status === 'finished';
  }

  hasGame(): boolean {
    return this.state.gameId !== null;
  }

  getCurrentMove(): Move | null {
    return this.state.moves.length > 0 
      ? this.state.moves[this.state.moves.length - 1]
      : null;
  }

  getMoveCount(): number {
    return this.state.moves.length;
  }

  getOptimalDistance(): number | null {
    return this.state.currentOptimalDistance;
  }

  // =============================================================================
  // Debug Helpers
  // =============================================================================

  debugState(): void {
    console.log('🐛 Current Game State:', {
      gameId: this.state.gameId,
      status: this.state.status,
      startPage: this.state.startPage,
      targetPage: this.state.targetPage,
      currentPage: this.state.currentPage,
      totalMoves: this.state.totalMoves,
      optimalDistance: this.state.currentOptimalDistance,
      moves: this.state.moves.map(m => `${m.step}: ${m.from_page_title} → ${m.to_page_title}`),
      optimalPaths: this.state.optimalPaths.length
    });
  }

  // =============================================================================
  // Event Router - Central dispatch for all game events
  // =============================================================================

  handleEvent(event: GameEvent): void {
    console.log(`📨 Game state: routing event ${event.type}`);
    
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
        console.warn('⚠️ Unknown event type in game state:', (event as any).type);
    }
  }
} 