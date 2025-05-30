# Wiki Arena - Startup Guide

## Quick Start (3 Terminals Required)

To run the complete Wiki Arena system, you need to start **3 components in order**:

### Terminal 1: MCP Server
```bash
cd mcp_server && uv run python server.py
```
**Expected Output:**
```
Starting simplified Wiki Arena MCP server...
```
**Status:** Keep this terminal running (no further output expected)

### Terminal 2: Backend API  
```bash
cd backend && uv run python -m backend.main
```
**Expected Output:**
```
backend.services.game_service: GameService initialized with wiki_arena config
INFO:     Started server process [XXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```
**Status:** Keep this terminal running, you'll see API requests logged here

### Terminal 3: Frontend UI
```bash
cd frontend && npm run dev
```
**Expected Output:**
```
> frontend@0.0.0 dev
> vite

  VITE v6.3.5  ready in 250 ms
  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```
**Status:** Keep this terminal running

## Access URLs

- **Frontend UI:** http://localhost:5173/
- **Backend API:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

## Startup Order Important!

**❗ Start in this exact order:**
1. **MCP Server first** - Provides Wikipedia navigation capabilities
2. **Backend second** - Depends on MCP server being available  
3. **Frontend last** - Connects to backend API

## Troubleshooting

### Backend Won't Start
If you get `ModuleNotFoundError: No module named 'websockets.legacy'`:
```bash
# Fix WebSocket dependency issue
uv add websockets==11.0.3

# Then restart backend
cd backend && uv run python -m backend.main
```

### Port Already in Use
If you get `ERROR: [Errno 98] Address already in use`:
```bash
# Kill existing processes
pkill -f "uvicorn" && pkill -f "python.*backend"

# Wait 2 seconds then restart
sleep 2 && cd backend && uv run python -m backend.main
```

### MCP Server Issues
If backend logs show MCP connection errors:
1. Make sure MCP server is running first
2. Check that `mcp_server/server.py` is running without errors
3. Restart backend after MCP server is stable

## Verification Steps

### 1. Check MCP Server
```bash
curl http://localhost:8000/health
```
**Expected:** `{"status":"healthy",...}`

### 2. Test Backend API
```bash
curl http://localhost:8000/stats
```
**Expected:** `{"active_games":X,"total_websocket_connections":Y,...}`

### 3. Test Complete System
1. Open http://localhost:5173/ in browser
2. Start a new race
3. Verify real-time updates appear in UI
4. Check backend terminal for WebSocket activity logs

## Normal Operation Logs

### MCP Server
- Usually silent after startup message
- May show HTTP requests during Wikipedia navigation

### Backend  
- Shows game creation: `Started game random_XXXXXX_XXXXXX`
- Shows WebSocket connections: `WebSocket connected to game XXXXX`
- Shows turn updates: `Broadcasting turn_played to game XXXXX`
- Shows game completion: `Background game XXXXX completed with status: won/lost_max_steps`

### Frontend
- Shows Vite dev server ready
- Hot reload messages when files change

## Features Working After Startup

✅ **Real-time WebSocket updates** - Live game progress in UI  
✅ **Background game execution** - Games run automatically  
✅ **Manual turn playing** - Step-by-step game control  
✅ **Clean resource cleanup** - No memory leaks or hanging processes  
✅ **Multiple concurrent games** - Scale to many simultaneous games  
✅ **Error handling** - Graceful failure recovery  

## Shutdown

To cleanly shut down:
1. **Frontend:** Ctrl+C in terminal 3
2. **Backend:** Ctrl+C in terminal 2  
3. **MCP Server:** Ctrl+C in terminal 1

Or kill all at once:
```bash
pkill -f "npm run dev" && pkill -f "python.*backend" && pkill -f "python.*server.py"
``` 