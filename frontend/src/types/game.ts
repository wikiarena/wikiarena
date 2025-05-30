export interface GameState {
  game_id: string;
  status: 'not_started' | 'in_progress' | 'won' | 'lost_max_steps' | 'lost_invalid_move' | 'error';
  steps: number;
  start_page: string;
  target_page: string;
  current_page?: string;
  moves: Move[];
  start_timestamp: string;
  end_timestamp?: string;
}

export interface Move {
  step: number;
  from_page_title: string;
  to_page_title?: string;
  model_response?: string;
  tool_call_attempt?: {
    tool_name: string;
    arguments: any;
  };
  error?: {
    type: string;
    message: string;
  };
  timestamp?: string;
}

export interface Page {
  title: string;
  url: string;
  links: string[];
}

export interface GameConfig {
  start_page_title: string;
  target_page_title: string;
  max_steps: number;
  model: {
    provider: string;
    model_name: string;
  };
} 