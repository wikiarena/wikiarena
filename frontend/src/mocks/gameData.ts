import type { GameState } from '../types/game';

export const mockGameData: GameState = {
  game_id: "claude_demo_game_123",
  status: "in_progress",
  steps: 3,
  start_page: "Artificial Intelligence",
  target_page: "Philosophy",
  current_page: "Machine Learning",
  start_timestamp: "2025-05-27T02:30:00Z",
  moves: [
    {
      step: 1,
      from_page_title: "Artificial Intelligence",
      to_page_title: "Machine Learning",
      model_response: "I need to navigate from 'Artificial Intelligence' to 'Philosophy'. Looking at the available links, I can see 'Machine Learning' which is a subset of AI that has connections to computational theory and cognitive science - areas that bridge towards philosophical concepts. This seems like a promising step towards Philosophy.",
      tool_call_attempt: {
        tool_name: "navigate",
        arguments: { page: "Machine Learning" }
      },
      timestamp: "2025-05-27T02:30:15Z"
    },
    {
      step: 2,
      from_page_title: "Machine Learning",
      to_page_title: "Cognitive Science",
      model_response: "Great! Now I'm on the Machine Learning page. I can see several promising links that could lead toward Philosophy. 'Cognitive Science' stands out as it's an interdisciplinary field that combines computer science, psychology, linguistics, and philosophy. This is a direct bridge to philosophical concepts about mind and knowledge.",
      tool_call_attempt: {
        tool_name: "navigate",
        arguments: { page: "Cognitive Science" }
      },
      timestamp: "2025-05-27T02:30:32Z"
    },
    {
      step: 3,
      from_page_title: "Cognitive Science",
      to_page_title: "Philosophy of Mind",
      model_response: "Perfect! Cognitive Science has many philosophical connections. I can see 'Philosophy of Mind' in the links, which is a major branch of philosophy that deals with consciousness, mental states, and the mind-body problem. This gets me very close to the general 'Philosophy' page as it's a core philosophical discipline.",
      tool_call_attempt: {
        tool_name: "navigate",
        arguments: { page: "Philosophy of Mind" }
      },
      timestamp: "2025-05-27T02:30:48Z"
    }
  ]
};

export const mockCompletedGame: GameState = {
  game_id: "claude_completed_game_456",
  status: "won",
  steps: 4,
  start_page: "Basketball",
  target_page: "Mathematics",
  current_page: "Mathematics",
  start_timestamp: "2025-05-27T02:00:00Z",
  end_timestamp: "2025-05-27T02:01:30Z",
  moves: [
    {
      step: 1,
      from_page_title: "Basketball",
      to_page_title: "Statistics",
      model_response: "I need to get from Basketball to Mathematics. Basketball has many statistical aspects - player performance metrics, game analytics, probability of shots, etc. 'Statistics' is a direct link I can see and it's a branch of mathematics.",
      tool_call_attempt: {
        tool_name: "navigate",
        arguments: { page: "Statistics" }
      },
      timestamp: "2025-05-27T02:00:15Z"
    },
    {
      step: 2,
      from_page_title: "Statistics",
      to_page_title: "Probability Theory",
      model_response: "Excellent! Statistics page has many mathematical connections. I can see 'Probability Theory' which is a fundamental mathematical framework that underlies statistics. This gets me deeper into pure mathematics.",
      tool_call_attempt: {
        tool_name: "navigate",
        arguments: { page: "Probability Theory" }
      },
      timestamp: "2025-05-27T02:00:45Z"
    },
    {
      step: 3,
      from_page_title: "Probability Theory",
      to_page_title: "Mathematical Analysis",
      model_response: "Great progress! Probability theory involves measure theory, integration, and advanced calculus. I can see 'Mathematical Analysis' which is a core area of pure mathematics dealing with limits, continuity, derivatives, and integrals.",
      tool_call_attempt: {
        tool_name: "navigate",
        arguments: { page: "Mathematical Analysis" }
      },
      timestamp: "2025-05-27T02:01:12Z"
    },
    {
      step: 4,
      from_page_title: "Mathematical Analysis",
      to_page_title: "Mathematics",
      model_response: "Perfect! Mathematical Analysis is a major branch of mathematics, and I can see a direct link to the main 'Mathematics' page. This completes the path from Basketball → Statistics → Probability Theory → Mathematical Analysis → Mathematics!",
      tool_call_attempt: {
        tool_name: "navigate",
        arguments: { page: "Mathematics" }
      },
      timestamp: "2025-05-27T02:01:28Z"
    }
  ]
};

export const mockFailedGame: GameState = {
  game_id: "claude_failed_game_789",
  status: "lost_invalid_move", 
  steps: 2,
  start_page: "Cooking",
  target_page: "Quantum Physics",
  current_page: "French Cuisine",
  start_timestamp: "2025-05-27T01:45:00Z",
  end_timestamp: "2025-05-27T01:46:15Z",
  moves: [
    {
      step: 1,
      from_page_title: "Cooking",
      to_page_title: "French Cuisine",
      model_response: "I need to navigate from Cooking to Quantum Physics. This is quite a challenge! Let me start by going to 'French Cuisine' and see if there are any scientific or cultural connections I can exploit.",
      tool_call_attempt: {
        tool_name: "navigate",
        arguments: { page: "French Cuisine" }
      },
      timestamp: "2025-05-27T01:45:30Z"
    },
    {
      step: 2,
      from_page_title: "French Cuisine",
      to_page_title: undefined,
      model_response: "Hmm, I'm looking at French Cuisine and I need to get to Quantum Physics. Maybe I can try 'Molecular Gastronomy' as it involves scientific principles in cooking... wait, let me try 'Albert Einstein' since he was involved in quantum physics development.",
      tool_call_attempt: {
        tool_name: "navigate",
        arguments: { page: "Albert Einstein" }
      },
      error: {
        type: "model_invalid_link",
        message: "Page 'Albert Einstein' is not in available links of 'French Cuisine'"
      },
      timestamp: "2025-05-27T01:46:15Z"
    }
  ]
}; 