// =============================================================================
// Core Page-Centric Game State Types
// =============================================================================

// Core page state representing the game at a specific page in navigation history
export interface PageState {
  pageTitle: string;
  moveIndex: number; // Which move brought us here (0 for start page)
  
  // Optimal path data (will arrive asynchronously)
  optimalPaths: string[][]; // Paths from this page to target
  distanceToTarget?: number;
  
  // Navigation context
  isStartPage: boolean;
  isTargetPage: boolean;
  visitedFromPage?: string; // Previous page title (for move edge)
  
  // Move distance assessment
  distanceChange?: number; // How this move affected distance to target
}

// Sequential game state - collection of page states
export interface GameSequence {
  gameId: string;
  startPage: string;
  targetPage: string;
  status: 'not_started' | 'in_progress' | 'finished';
  
  // Core sequential data
  pageStates: PageState[]; // One per unique page visited, in order
  currentPageIndex: number; // Index of latest page reached in actual game
  viewingPageIndex: number; // Index of page currently being viewed (for stepping)
  
  // Progress tracking
  initialOptimalDistance: number | null; // Initial distance from start to target
  
  // Rendering mode
  renderingMode: 'live' | 'stepping';
}

// =============================================================================
// Graph Visualization Types
// =============================================================================

// Page node for graph visualization - represents a Wikipedia page
export interface PageNode {
  pageTitle: string;
  type: 'start' | 'target' | 'visited' | 'optimal_path';
  
  // Derived from PageState or optimal paths
  distanceToTarget?: number;
  distanceChange?: number; // For visited pages only
  
  // Positioning (for D3 force simulation)
  x?: number;
  y?: number;
  fx?: number; // Fixed positions
  fy?: number;
}

// Navigation edge - represents a move or potential move
export interface NavigationEdge {
  id: string;
  sourcePageTitle: string;
  targetPageTitle: string;
  type: 'move' | 'optimal_path';
  
  // For move edges only
  moveIndex?: number;
  distanceChange?: number; // How this move affected distance to target
}

// Complete graph data for visualization
export interface PageGraphData {
  pages: PageNode[];
  edges: NavigationEdge[];
}

// =============================================================================
// WebSocket Event Types
// =============================================================================

// Base interface for all game events
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
  from_page_title?: string;
  to_page_title?: string;
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
  distanceChange?: number; // Positive = got closer, negative = got further, 0 = same, undefined = unknown
}

// =============================================================================
// Legacy Game State Types (for backward compatibility during transition)
// =============================================================================

export interface GameState {
  gameId: string | null;
  status: 'not_started' | 'in_progress' | 'finished';
  startPage: string | null;
  targetPage: string | null;
  currentPage: string | null;
  moves: Move[]; // All moves for page history
  viewingMoves?: Move[]; // Moves up to viewing index for graph rendering
  optimalPaths: string[][];
  currentDistance: number | null;
  totalMoves: number;
  success: boolean | null;
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
// Utility Types
// =============================================================================

export type EventHandler<T extends GameEvent = GameEvent> = (event: T) => void;

export type RenderingMode = 'live' | 'stepping';

export interface StartGameRequest {
  start_page?: string;
  target_page?: string;
}