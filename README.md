# Wiki Arena - LLM Wikipedia Navigation Eval

## Command Line Interface

```bash
uv run python src/wiki_arena/main.py -m "gpt-4.1-nano-2025-04-14"
```

## Web Interface

See [STARTUP.md](STARTUP.md) for complete setup instructions.

**TL;DR:** Start 2 terminals:
```bash
# Terminal 1: Backend and MCP Server
cd ~/wiki-arena && uv run uvicorn src.backend.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Frontend UI
cd ~/wiki-arena/frontend && npm run dev-game
```
Then open http://localhost:3000/
---

# game
https://en.wikipedia.org/wiki/Wikipedia:Wiki_Game
> In a Wikipedia race, two players race from the same start page for one of two objectives:
1. Get to the target page using the fewest number of links
2. Get to the target page as fast as possible


