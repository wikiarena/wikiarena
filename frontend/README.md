# Wiki Arena Frontend

Event-driven frontend for viewing Wikipedia navigation games in real-time.

## Architecture

This frontend uses a clean, event-driven architecture built with vanilla TypeScript:

- **WebSocket Client** (`websocket.ts`) - Handles real-time communication with backend
- **Game State Manager** (`game-state.ts`) - Central state management for game data  
- **UI Controller** (`ui-controller.ts`) - DOM updates and user interactions
- **Main App** (`main.ts`) - Orchestrates all components together
- **Type Definitions** (`types.ts`) - Complete TypeScript type system

## Development

### Setup
```bash
npm install
```

### Development Server
```bash
npm run dev-game
```
Opens the game viewer at `http://localhost:3000/game.html`

### Build
```bash
npm run build
```
Outputs to `dist/` directory

## Usage

1. **Connect**: Click "Connect" to establish WebSocket connection to backend
2. **Start Game**: Click "Start New Game" to begin a new Wikipedia navigation game
3. **Watch**: View real-time game progress with optimal path visualization

## Features

- **Real-time Updates**: WebSocket events update UI instantly
- **Connection Management**: Automatic reconnection with visual status
- **Game Visualization**: Shows moves, optimal paths, and move quality
- **Error Handling**: User-friendly error messages and recovery
- **Debug Interface**: `window.wikiArena.debug()` for development

## Event Flow

```
Backend WebSocket → Game State Manager → UI Controller → DOM Updates
```

The frontend listens for these events:
- `GAME_STARTED` - Initialize new game display
- `GAME_MOVE_COMPLETED` - Add new move to visualization  
- `OPTIMAL_PATHS_UPDATED` - Update path analysis and move quality
- `GAME_FINISHED` - Display final game results

## Technology Stack

- **TypeScript** - Type-safe development
- **Vite** - Fast development and building
- **D3.js** - Graph visualization (ready for implementation)
- **Vanilla DOM** - Lightweight, no framework overhead

## File Structure

```
frontend/
├── game.html              # Main game viewer page
├── main.ts                # Application entry point
├── websocket.ts           # WebSocket client
├── game-state.ts          # State management
├── ui-controller.ts       # UI updates
├── types.ts               # TypeScript definitions
├── package.json           # Dependencies
├── vite.config.ts         # Build configuration
└── tsconfig.*.json        # TypeScript configuration
```
