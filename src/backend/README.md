# Wiki Arena Backend API

A FastAPI backend for running Wikipedia navigation games with real-time updates using **event-driven architecture**.

## Architecture Overview

The backend follows an **event-driven architecture** with clear separation of concerns:

```
src/backend/
├── main.py                      # FastAPI app + event system setup
├── config.py                    # Configuration management
├── dependencies.py              # Dependency injection
│
├── api/                         # HTTP endpoints
│   ├── games.py                # Game management REST API
│   └── solver.py               # Path solving endpoints
│
├── models/                      # API data models
│   └── api_models.py           # Request/response Pydantic models
│
├── coordinators/               # Business orchestration
│   └── game_coordinator.py    # Game lifecycle management
│
├── handlers/                   # Event handlers (stateless & reactive)
│   ├── websocket_handler.py   # WebSocket broadcasting
│   └── optimal_path_handler.py # Parallel optimal task solver
│
└── websockets/                 # Real-time communication
    └── game_hub.py            # WebSocket connection management
```

## Event-Driven Flow

Our architecture implements the **ARCHITECTURE_V2.md** vision with true event-driven, non-blocking gameplay:

1. **GameManager** (core library) emits events when moves complete
2. **EventBus** routes events to registered handlers
3. **WebSocketHandler** broadcasts updates to connected clients **immediately**
4. **OptimalPathHandler** triggers optimal task solver **in parallel** (non-blocking)
5. **GameCoordinator** manages game lifecycles and orchestrates between layers

### Key Benefits

- ✅ **Non-blocking**: Game moves complete instantly, analysis happens in background
- ✅ **Parallel processing**: task solver runs alongside game execution  
- ✅ **Real-time updates**: WebSocket events sent immediately on game moves
- ✅ **Clean separation**: Coordinators handle business logic, handlers react to events
- ✅ **Scalable**: Easy to add new event handlers without changing core logic

## Features

### Core Capabilities ✅
- ✅ Start new games with configurable parameters
- ✅ Play turns step-by-step or run games in background
- ✅ Get game state and status
- ✅ Real-time WebSocket updates via event system
- ✅ Parallel optimal task solver (non-blocking)
- ✅ Clean game resource management
- ✅ Auto-generated API documentation

### Event-Driven Features ✅
- ✅ **Immediate move updates**: Games don't wait for task solver
- ✅ **Background task solver**: Optimal paths calculated in parallel
- ✅ **Multiple event handlers**: WebSocket + task solver + future storage/metrics
- ✅ **Error isolation**: Failing handlers don't stop game execution
- ✅ **Graceful shutdown**: Proper cleanup of games and background tasks

## Quick Start

### Prerequisites

1. Start the MCP server:
```bash
cd mcp_server && uv run python server.py
```

2. Start the FastAPI backend:
```bash
uv run python -m backend.main
```

The backend will automatically:
- Initialize the EventBus
- Connect to MCP server
- Register event handlers (WebSocket + PathAnalysis)
- Start accepting HTTP and WebSocket connections

### API Endpoints

#### Core Game API
- **Health Check**: `GET /health`
- **API Documentation**: `GET /docs`
- **Start Game**: `POST /api/games`
- **Start Background Game**: `POST /api/games?background=true`
- **Get Game State**: `GET /api/games/{game_id}`
- **Play Turn**: `POST /api/games/{game_id}/turn`
- **Terminate Game**: `DELETE /api/games/{game_id}`

#### Monitoring & Stats
- **List Active Games**: `GET /api/games`

#### Real-Time Updates
- **WebSocket Connection**: `WS /api/games/{game_id}/ws`

### Example Usage

#### Start a Background Game
```bash
curl -X POST "http://localhost:8000/api/games?background=true" \
  -H "Content-Type: application/json" \
  -d '{
    "start_page": "Computer Science",
    "target_page": "Philosophy", 
    "max_steps": 15,
    "model_provider": "random",
    "model_name": "random"
  }'
```

#### Connect to WebSocket for Real-Time Updates
```javascript
const ws = new WebSocket('ws://localhost:8000/api/games/{game_id}/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data.type, data);
};
```

### WebSocket Events

The event-driven system sends real-time WebSocket messages:

- **`connection_established`**: Initial connection confirmation
- **`GAME_STARTED`**: Game has been initialized
- **`GAME_MOVE_COMPLETED`**: A move was completed (sent immediately)
- **`OPTIMAL_PATHS_UPDATED`**: task solver completed (sent when ready)
- **`GAME_ENDED`**: Game has finished

Example move completion event:
```json
{
  "type": "GAME_MOVE_COMPLETED",
  "game_id": "random_20250607_140544_e58ea8ce", 
  "move": {
    "step": 3,
    "from_page_title": "Computer Science",
    "to_page_title": "Mathematics",
    "model_response": "Navigating to Mathematics..."
  },
  "game_over": false,
  "current_page": "Mathematics",
  "steps": 3,
  "status": "in_progress"
}
```

Example task solver update (sent separately):
```json
{
  "type": "OPTIMAL_PATHS_UPDATED",
  "game_id": "random_20250607_140544_e58ea8ce",
  "optimal_paths": [["Mathematics", "Science", "Philosophy"]],
  "optimal_path_length": 3,
  "move_quality": "improved"
}
```

## Key Components

### GameCoordinator (`coordinators/game_coordinator.py`)
- **Manages game lifecycles**: Create, run, terminate games
- **Orchestrates between layers**: Core library ↔ Web API
- **Handles background execution**: Async game runs with proper cleanup
- **Model conversion**: Core GameState ↔ API responses

### Event Handlers (`handlers/`)
- **WebSocketHandler**: Reacts to game events, broadcasts to connected clients
- **OptimalPathHandler**: Triggers parallel optimal task solver without blocking games
- **Stateless & reactive**: Pure event consumers, no shared state

### WebSocket Manager (`websockets/game_hub.py`)
- **Connection management**: Per-game WebSocket connections
- **Broadcasting**: Send events to all clients watching a game
- **Automatic cleanup**: Remove failed connections gracefully

## Data Models

The API uses Pydantic models that integrate with the core library:

- `StartGameRequest`: Configuration for starting new games
- `GameStateResponse`: Complete game state for API responses  
- `MoveResponse`: Individual move data
- `GameEvent`: Core library events (from EventBus)

## Testing

Run comprehensive tests of the event-driven architecture:

```bash
# Test basic functionality
uv run python -c "
from src.backend.main import app
print('✅ Backend imports successfully')
"

# Test with real server (in separate terminal)
uv run python -m backend.main
```

## Next Steps

The event-driven foundation enables:

- [ ] **Storage handlers**: Automatic game persistence via events
- [ ] **Metrics handlers**: Real-time analytics and monitoring  
- [ ] **Racing system**: Multi-game coordination via EventBus
- [ ] **Advanced visualization**: Rich task solver data for frontend
- [ ] **Scalability**: Distributed event processing if needed 