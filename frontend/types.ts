import { ModelInfo } from './model-service.js';
// TODO(hunter): should ModelInfo be in types.ts?

// =============================================================================
// Core Task-Centric Data Types
// =============================================================================

// Player object that composes all data related to a single competitor
export interface Player {
  playerIndex: number;
  color: string;
  gameId: string;
  model: ModelInfo;
  gameSequence: GameSequence;
  gameResult?: GameResult;
}

// Task object containing multiple games competing on same start/target pages
export interface Task {
  startPage: string;
  targetPage: string;
  shortestPathLength: number | undefined; // NOTE: will be undefined until initial shortest paths are found
  players: Player[];
  
  // Viewing information
  renderingMode: 'live' | 'stepping';
  viewingPageIndex: number;
  currentPageIndex: number;
}

// Game sequence object per player
export interface GameSequence {
  gameId: string; // for websocket connection
  status: string;
  pageStates: PageState[]; // sequence of page states
}

// Page state representing the game at a specific page in navigation history
export interface PageState {
  gameId: string; // required for multi-player support
  pageTitle: string;
  moveIndex: number; // Which move brought us here (0 for start page)
  
  // Optimal path data (will arrive asynchronously)
  optimalPaths: string[][]; // Paths from this page to target
  distanceToTarget?: number;
  distanceChange?: number; // How this move affected distance to target
  
  // Navigation context
  isStartPage: boolean; // TODO(hunter): this is not used anywhere
  isTargetPage: boolean; // this isn't really used either
  visitedFromPage?: string; // Previous page title (for move edge)
}

// =============================================================================
// Graph Visualization Types
// =============================================================================

// Page node for graph visualization - represents a Wikipedia page
export interface PageNode {
  pageTitle: string;
  type: 'start' | 'target' | 'visited' | 'optimal_path' | 'error'; // ‼️
  distanceToTarget?: number; // Same for all visits - property of the graph (wikipedia)
  
  // Array of visits from games (only when node is visited during a game)
  visits: Array<{
    gameId: string;
    moveIndex: number;
    distanceChange?: number;
  }>;
  
  // Positioning (for D3 force simulation)
  x?: number;
  y?: number;
  fx?: number; // Fixed positions
  fy?: number;
}

// Navigation edge - represents a move or potential move
export interface NavigationEdge {
  id: string; // includes game_id for uniqueness
  sourcePageTitle: string;
  targetPageTitle: string;
  type: 'move' | 'optimal_path';
  
  // For move edges only
  moveIndex?: number;
  distanceChange?: number; // How this move affected distance to target
}

export type SpawnDirection = 'clockwise' | 'counter-clockwise';

// Complete graph data for visualization
export interface PageGraphData {
  pages: PageNode[];
  edges: NavigationEdge[];
  colorMap: Map<string, string>; // gameId -> color
  spawnDirectionMap: Map<string, SpawnDirection>; // gameId -> spawn direction
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
  type: 'CONNECTION_ESTABLISHED';
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
      moves: Array<{
        step: number;
        from_page_title: string;
        to_page_title: string;
      }>;
    };
    solver_results?: Array<{
      optimal_paths: string[][];
      optimal_path_length: number;
      from_page_title: string;
      to_page_title: string;
    }>;
  };
}

export interface GameMoveCompletedEvent extends BaseGameEvent {
  type: 'GAME_MOVE_COMPLETED';
  move: Move;
  status: string;
}

export interface OptimalPathsUpdatedEvent extends BaseGameEvent {
  type: 'OPTIMAL_PATHS_UPDATED';
  from_page_title?: string;
  to_page_title?: string;
  optimal_paths: string[][];
  optimal_path_length?: number;
}

export interface GameEndedEvent extends BaseGameEvent {
  type: 'GAME_ENDED';
  game_result: {
    game_id: string;
    config: {
      start_page_title: string;
      target_page_title: string;
      max_steps: number;
      system_prompt_template?: string;
    };
    model_id: string;
    status: string;
    steps: number;
    moves: Array<{
      step: number;
      from_page_title: string;
      to_page_title: string;
      // Additional move fields may be added by backend
    }>;
    context: Array<{
      role: string;
      content: string;
      // Additional context fields may vary by message type
    }>;
    start_timestamp: string; // ISO datetime string # TODO(hunter): wtf why are my timestamps datetimes
    end_timestamp: string;   // ISO datetime string
    error_message?: string;
    
    // Aggregated API metrics
    total_input_tokens: number;
    total_output_tokens: number;
    total_tokens: number;
    total_estimated_cost_usd: number;
    total_api_time_ms: number;
    average_response_time_ms: number;
    api_call_count: number;
  };
}

// TODO(hunter): should this be a different event type since it is above game level? (has task_id)
export interface TaskEndedEvent extends BaseGameEvent {
  type: 'TASK_ENDED';
  start_page: Page;
  target_page: Page;
}

export type GameEvent = 
  | ConnectionEstablishedEvent
  | GameMoveCompletedEvent 
  | OptimalPathsUpdatedEvent 
  | GameEndedEvent
  | TaskEndedEvent;

// =============================================================================
// Core Game Data Types
// =============================================================================

export interface Page {
  title: string;
  url: string;
  text?: string;
  links?: string[];
}

export interface Move {
  from_page_title: string;
  to_page_title: string;
  step: number;
  error?: string | undefined;
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

// Model configuration interface to match models.json structure
export interface ModelConfig {
  provider: string;
  input_cost_per_1m_tokens: number;
  output_cost_per_1m_tokens: number;
  default_settings: {
    max_tokens: number;
  };
}

// Game result object for completed games
export interface GameResult {
  gameId: string;
  modelId: string;
  config: {
    startPageTitle: string;
    targetPageTitle: string;
    maxSteps: number;
    systemPromptTemplate?: string;
  };
  status: string;
  steps: number;
  errorMessage?: string;
  
  // Performance metrics
  totalEstimatedCostUsd: number;
  totalApiTimeMs: number;
  averageResponseTimeMs: number;
  apiCallCount: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  totalTokens: number;
  
  // Timestamps
  startTimestamp: string;
  endTimestamp: string;
}
