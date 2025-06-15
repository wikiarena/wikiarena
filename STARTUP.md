# Wiki Arena - Startup Guide

## Database

make sure the databse is setup under `/database/wiki_graph.sqlite`

## Development

### Backend and MCP Server

First Terminal:
``` 
cd ~/wiki-arena && uv run uvicorn src.backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

Second Terminal:
```
cd ~/wiki-arena/frontend && npm run dev-game
```

# Teardown

just Ctrl+C in each terminal

## By force

Or kill all at once:
```bash
pkill -f "npm run dev*" && pkill -f "python.*backend" && pkill -f "python.*server.py"
``` 