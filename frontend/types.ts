// =============================================================================
// WebSocket Event Types
// =============================================================================

// Updated to match backend event format (flat structure with "type")
export interface BaseGameEvent {
  type: string;
  game_id: string;
  timestamp?: string;
}

export interface ConnectionEstablishedEvent extends BaseGameEvent {
  type: 'connection_established';
  message: string;
  complete_state?: {
    game?: {
      game_id: string;
      config: {
        start_page_title: string;
        target_page_title: string;
        max_steps: number;
      };
      status: string;
      steps: number;
      current_page?: {
        title: string;
        // TODO(hunter): add other content here later
      };
      move_history: Array<{
        step: number;
        from_page_title: string;
        to_page_title: string;
      }>;
    };
    solver?: {
      optimal_paths: string[][];
      optimal_path_length: number;
      from_page_title: string;
      to_page_title: string;
      timestamp: string;
    };
    timestamp: string;
  };
}

export interface GameStartedEvent extends BaseGameEvent {
  type: 'GAME_STARTED';
  start_page: Page;
  target_page: Page;
}

export interface GameMoveCompletedEvent extends BaseGameEvent {
  type: 'GAME_MOVE_COMPLETED';
  move: Move;
  current_page: Page;
}

export interface OptimalPathsUpdatedEvent extends BaseGameEvent {
  type: 'OPTIMAL_PATHS_UPDATED';
  current_page?: string;
  target_page?: string;
  optimal_paths: string[][];
  optimal_path_length?: number;
}

export interface GameFinishedEvent extends BaseGameEvent {
  type: 'GAME_FINISHED';
  final_move: Move;
  total_moves: number;
  success: boolean;
  optimal_path_length: number;
}

export type GameEvent = 
  | ConnectionEstablishedEvent
  | GameStartedEvent 
  | GameMoveCompletedEvent 
  | OptimalPathsUpdatedEvent 
  | GameFinishedEvent;

// =============================================================================
// Core Game Data Types
// =============================================================================

export interface Page {
  title: string;
  links: string[];
  content?: string;
}

export interface Move {
  from_page_title: string;
  to_page_title: string;
  step: number;
  timestamp?: string | null;
  model_response?: string;
}

// =============================================================================
// Game State Types
// =============================================================================

export interface GameState {
  gameId: string | null;
  status: 'not_started' | 'in_progress' | 'finished';
  startPage: string | null;
  targetPage: string | null;
  currentPage: string | null;
  moves: Move[];
  optimalPaths: string[][];
  currentOptimalDistance: number | null;
  totalMoves: number;
  success: boolean | null;
}

// =============================================================================
// Graph Visualization Types
// =============================================================================

export interface GraphNode {
  id: string;
  title: string;
  type: 'start' | 'target' | 'move' | 'optimal_path';
  x?: number;
  y?: number;
  fx?: number; // Fixed x position for D3 force simulation
  fy?: number; // Fixed y position for D3 force simulation
  moveNumber?: number;
  quality?: 'good' | 'neutral' | 'bad' | 'unknown';
  
  // New properties for move quality calculation
  distanceToTarget?: number; // Shortest path length to target (undefined if unknown)
  qualityCalculated?: boolean; // Whether we've calculated the move quality yet
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: 'move' | 'optimal_path';
  moveNumber?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// =============================================================================
// WebSocket Connection Types
// =============================================================================

export interface WebSocketConfig {
  url: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

export interface ConnectionStatus {
  connected: boolean;
  connecting: boolean;
  error: string | null;
  reconnectAttempts: number;
}

// =============================================================================
// UI State Types
// =============================================================================

export interface UIState {
  selectedGameId: string | null;
  showControls: boolean;
  showDebugInfo: boolean;
  graphViewport: {
    zoom: number;
    panX: number;
    panY: number;
  };
}

// =============================================================================
// Event Handler Types
// =============================================================================

export type EventHandler<T extends GameEvent = GameEvent> = (event: T) => void;

export interface EventHandlers {
  onGameStarted: EventHandler<GameStartedEvent>;
  onMoveCompleted: EventHandler<GameMoveCompletedEvent>;
  onOptimalPathsUpdated: EventHandler<OptimalPathsUpdatedEvent>;
  onGameFinished: EventHandler<GameFinishedEvent>;
}

// =============================================================================
// API Types (for starting games)
// =============================================================================

export interface StartGameRequest {
  start_page?: string;
  target_page?: string;
}

export interface StartGameResponse {
  game_id: string;
  message: string;
} 