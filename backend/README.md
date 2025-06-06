# Wiki Arena Backend API

A FastAPI backend for running Wikipedia navigation games with real-time updates.

## Features

### Phase 1 ✅
- ✅ Start new games with configurable parameters
- ✅ Play turns step-by-step
- ✅ Get game state and status
- ✅ Full integration with existing wiki_arena core
- ✅ Auto-generated API documentation
- ✅ Health checks and error handling

### Phase 2 ✅
- ✅ **WebSocket support for real-time updates**
- ✅ **Background game execution**
- ✅ **Live game streaming via WebSocket**
- ✅ **Enhanced API with stats and monitoring**
- ✅ **Non-blocking game execution**
- ✅ **Connection management and cleanup**

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

### API Endpoints

#### Core Game API
- **Health Check**: `GET /health`
- **API Documentation**: `GET /docs`
- **Start Game**: `POST /api/games`
- **Start Background Game**: `POST /api/games?background=true`
- **Get Game State**: `GET /api/games/{game_id}`
- **Play Turn**: `POST /api/games/{game_id}/turn`

#### Monitoring & Stats
- **List Active Games**: `GET /api/games`
- **API Stats**: `GET /stats`

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
  console.log('Game update:', data.type, data);
};
```

#### Monitor API Stats
```bash
curl http://localhost:8000/stats
```

### WebSocket Events

The WebSocket connection sends JSON messages with the following event types:

- **`connection_established`**: Initial connection confirmation
- **`game_started`**: Game has been initialized
- **`turn_played`**: A turn has been completed (includes move details)
- **`game_finished`**: Game has ended (includes final status)
- **`error`**: An error occurred during game execution

Example WebSocket message:
```json
{
  "type": "turn_played",
  "game_id": "random_20250527_225109_4a0c5637",
  "timestamp": "2025-05-27T22:51:15.123456",
  "game_state": {
    "game_id": "random_20250527_225109_4a0c5637",
    "status": "in_progress",
    "steps": 3,
    "current_page": "Mathematics",
    "moves": [...]
  },
  "move": {
    "step": 3,
    "from_page_title": "Computer Science",
    "to_page_title": "Mathematics",
    "model_response": "Randomly selected link: Mathematics"
  },
  "game_over": false,
  "background": true
}
```

### Test the API

#### Basic API Test
```bash
uv run python backend/test_api.py
```

#### Phase 2 Features Test
```bash
uv run python backend/test_phase2.py
```

## Architecture

The backend follows a service-oriented architecture with real-time capabilities:

- **`main.py`**: FastAPI application with CORS, WebSocket support, and error handling
- **`api/games.py`**: REST and WebSocket endpoints for game operations
- **`services/game_service.py`**: Enhanced wrapper around GameManager with background execution
- **`websockets/game_hub.py`**: WebSocket connection manager for real-time updates
- **`models/api_models.py`**: Pydantic models for requests/responses
- **`config.py`**: Configuration management

### Background Execution Flow

1. **Start Background Game**: `POST /api/games?background=true`
2. **Game Runs Automatically**: Service creates asyncio task for game execution
3. **Real-Time Updates**: WebSocket broadcasts each turn as it happens
4. **Automatic Cleanup**: Game resources cleaned up when finished

### WebSocket Connection Management

- **Per-Game Connections**: Each game can have multiple WebSocket connections
- **Automatic Cleanup**: Failed connections are automatically removed
- **Broadcast System**: Updates sent to all connected clients for a game
- **Connection Tracking**: Stats endpoint shows active connections

## Data Models

The API uses Pydantic models that match the frontend TypeScript interfaces:

- `StartGameRequest`: Configuration for starting a new game
- `GameStateResponse`: Complete game state (matches frontend `GameState`)
- `MoveResponse`: Individual move data (matches frontend `Move`)

## Next Steps (Phase 3)

- [ ] Multi-game racing support
- [ ] Race orchestration and winner determination
- [ ] Race-specific WebSocket updates
- [ ] Leaderboards and game history
- [ ] Advanced game analytics 