# Wikipedia Task Selector

The `WikipediaTaskSelector` module provides functionality for randomly selecting pairs of Wikipedia pages for use in the Wiki Arena game. It's designed to be standalone and decoupled from the rest of the application logic.

## Features

- ✅ Randomly selects Wikipedia page pairs using the Wikipedia API
- ✅ Ensures start and target pages are different
- ✅ Filters out tag pages and special pages
- ✅ Configurable exclusion rules
- ✅ Both synchronous and asynchronous support
- ✅ Robust error handling and retry logic
- ✅ Comprehensive logging

## Quick Start

### Basic Usage

```python
from wiki_arena.wikipedia.task_selector import get_random_task

# Simple one-liner to get a random task
task = get_random_task()

if task:
    print(f"Start: {task.start_page}")
    print(f"Target: {task.target_page}")
```

### Async Usage

```python
import asyncio
from wiki_arena.wikipedia.task_selector import get_random_task_async

async def main():
    task = await get_random_task_async()
    if task:
        print(f"Start: {task.start_page}")
        print(f"Target: {task.target_page}")

asyncio.run(main())
```

### Integration with Game Config

```python
from wiki_arena.wikipedia.task_selector import get_random_task_async
from wiki_arena.data_models.game_models import GameConfig

async def create_game():
    # Generate random pages
    task = await get_random_task_async()
    
    if not task:
        raise Exception("Failed to generate page pair")
    
    # Create game configuration
    game_config = GameConfig(
        start_page_title=task.start_page,
        target_page_title=task.target_page,
        max_steps=30,
        model_provider="openai",
        model_settings={}
    )
    
    return game_config
```

## Classes and Functions

### Task

A data class representing a task for a game.

```python
class Task(BaseModel):
    start_page_title: str
    target_page_title: str
```

**Validation**: Automatically validates that start and target pages are different.

### WikipediaTaskSelector

The main class for selecting random Wikipedia tasks.

#### Constructor

```python
WikipediaTaskSelector(
    language: str = "en",
    max_retries: int = 10,
    excluded_prefixes: Optional[Set[str]] = None
)
```

**Parameters:**
- `language`: Wikipedia language code (default: "en")
- `max_retries`: Maximum number of retries when selecting pages
- `excluded_prefixes`: Set of prefixes to exclude (see default exclusions below)

#### Methods

##### `select_page_pair() -> Optional[PagePair]`
Selects a pair of different, valid Wikipedia pages synchronously.

##### `select_page_pair_async() -> Optional[PagePair]`
Async version of `select_page_pair()` for use in async contexts.

##### `select_valid_page() -> Optional[str]`
Selects a single valid page for the game.

##### `get_random_pages(count: int = 10) -> List[str]`
Gets a list of random Wikipedia page titles from the API.

### Convenience Functions

#### `get_random_page_pair(...) -> Optional[PagePair]`
Convenience function to get a random page pair synchronously.

#### `get_random_page_pair_async(...) -> Optional[PagePair]`
Async convenience function to get a random page pair.

## Default Exclusions

By default, the following page types are excluded:

- `Tag:` - Tag pages
- `Category:` - Category pages
- `File:` - File/media pages
- `Template:` - Template pages
- `Help:` - Help pages
- `Wikipedia:` - Wikipedia namespace pages
- `User:` - User pages
- `User talk:` - User talk pages
- `Template talk:` - Template talk pages
- `Category talk:` - Category talk pages
- `Portal:` - Portal pages
- `Project:` - Project pages
- `MediaWiki:` - MediaWiki namespace pages
- `Module:` - Module pages
- `Draft:` - Draft pages

## Custom Exclusions

You can provide your own set of exclusions:

```python
from wiki_arena.wikipedia.page_selector import WikipediaPageSelector

# Add custom exclusions
custom_exclusions = {
    "Category:",
    "File:",
    "Template:",
    "List of",          # Exclude list pages
    "Timeline of",      # Exclude timeline pages
    "Deaths in",        # Exclude death listing pages
    "Births in",        # Exclude birth listing pages
}

selector = WikipediaPageSelector(excluded_prefixes=custom_exclusions)
page_pair = selector.select_page_pair()
```

## Error Handling

The module includes comprehensive error handling:

- **API Failures**: Retries with exponential backoff
- **Invalid Pages**: Automatic filtering and retry
- **Network Issues**: Proper timeout and exception handling
- **Validation Errors**: Clear error messages for invalid page pairs

### Example Error Handling

```python
from wiki_arena.wikipedia.page_selector import get_random_page_pair

try:
    page_pair = get_random_page_pair(max_retries=5)
    
    if not page_pair:
        print("Failed to generate page pair after retries")
        # Handle failure case
    else:
        print(f"Success: {page_pair.start_page} -> {page_pair.target_page}")
        
except Exception as e:
    print(f"Error during page selection: {e}")
    # Handle exception
```

## Logging

The module uses Python's standard logging framework. Configure logging to see detailed information:

```python
import logging

# Enable debug logging to see detailed selection process
logging.basicConfig(level=logging.DEBUG)

# Or just info for basic status updates
logging.basicConfig(level=logging.INFO)
```

Log levels:
- **DEBUG**: Detailed selection process, API calls, validation steps
- **INFO**: High-level status updates, successful selections
- **WARNING**: Retry attempts, validation failures
- **ERROR**: API failures, selection failures

## Configuration

### Multiple Languages

```python
# Select from German Wikipedia
selector = WikipediaPageSelector(language="de")
page_pair = selector.select_page_pair()
```

### Retry Configuration

```python
# More aggressive retry strategy
selector = WikipediaPageSelector(max_retries=20)
page_pair = selector.select_page_pair()
```

### Combined Configuration

```python
selector = WikipediaPageSelector(
    language="en",
    max_retries=15,
    excluded_prefixes={"Category:", "File:", "List of"}
)
```

## Performance Considerations

- **Batch Fetching**: The module fetches multiple random pages per API call to improve efficiency
- **Caching**: Consider implementing caching for repeated selections
- **Rate Limiting**: The Wikipedia API has rate limits; the module includes appropriate delays
- **Async Support**: Use async functions in async contexts to avoid blocking

## Integration Examples

### CLI Tool

```python
#!/usr/bin/env python3
import asyncio
from wiki_arena.wikipedia.page_selector import get_random_page_pair_async

async def main():
    print("Generating random Wikipedia game...")
    page_pair = await get_random_page_pair_async()
    
    if page_pair:
        print(f"🎯 Challenge: Navigate from '{page_pair.start_page}' to '{page_pair.target_page}'")
        print(f"🔗 Start URL: https://en.wikipedia.org/wiki/{page_pair.start_page.replace(' ', '_')}")
    else:
        print("❌ Failed to generate challenge")

if __name__ == "__main__":
    asyncio.run(main())
```

### Web API Endpoint

```python
from fastapi import FastAPI, HTTPException
from wiki_arena.wikipedia.page_selector import get_random_page_pair_async

app = FastAPI()

@app.get("/random-challenge")
async def get_random_challenge():
    page_pair = await get_random_page_pair_async()
    
    if not page_pair:
        raise HTTPException(status_code=500, detail="Failed to generate page pair")
    
    return {
        "start_page": page_pair.start_page,
        "target_page": page_pair.target_page,
        "start_url": f"https://en.wikipedia.org/wiki/{page_pair.start_page.replace(' ', '_')}",
        "target_url": f"https://en.wikipedia.org/wiki/{page_pair.target_page.replace(' ', '_')}"
    }
```

## Testing

The module includes comprehensive test coverage. Run tests with:

```bash
python test_page_selector.py
```

Test scenarios include:
- ✅ Synchronous and asynchronous selection
- ✅ Custom exclusion rules
- ✅ Multiple page generation
- ✅ Error handling and validation
- ✅ Integration patterns

## Dependencies

- `requests`: For Wikipedia API calls
- `asyncio`: For async support
- `dataclasses`: For PagePair data structure
- `typing`: For type hints
- `logging`: For comprehensive logging

## API Reference

The module uses the Wikipedia API's `list=random` endpoint:

- **Endpoint**: `https://en.wikipedia.org/w/api.php`
- **Parameters**:
  - `action=query`
  - `list=random`
  - `rnnamespace=0` (main namespace only)
  - `rnfilterredir=nonredirects` (exclude redirects)
  - `rnlimit=20` (number of pages to fetch)

## Troubleshooting

### Common Issues

1. **No pages returned**: Check network connectivity and Wikipedia API status
2. **All pages filtered out**: Adjust exclusion rules or increase retry count
3. **Timeout errors**: Increase timeout or check network stability
4. **Rate limiting**: Add delays between requests or reduce batch size

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.getLogger('wiki_arena.page_selector').setLevel(logging.DEBUG)
```

## Future Enhancements

Potential improvements for the module:

- [x] **Ensure that source page has links out and target page has links in** ✅ IMPLEMENTED
- [ ] Page difficulty estimation based on link count
- [ ] Geographic/topic-based filtering
- [ ] Caching layer for performance
- [ ] Metrics collection for success rates
- [ ] Support for multiple Wikipedia languages simultaneously
- [ ] Page existence validation before selection
- [ ] Integration with Wikipedia's category system for themed challenges

## Link Validation

The module now supports optional link validation to ensure game viability:

### Configuration

Use `LinkValidationConfig` to enable link validation:

```python
from wiki_arena.wikipedia.page_selector import WikipediaPageSelector, LinkValidationConfig

# Ensure start page has outgoing links
config = LinkValidationConfig(
    require_outgoing_links=True,
    min_outgoing_links=5  # Require at least 5 outgoing links
)

selector = WikipediaPageSelector(link_validation=config)
page_pair = selector.select_page_pair()
```

### Link Validation Options

#### Outgoing Links (Start Page)
Ensures the start page has sufficient links to navigate from:

```python
config = LinkValidationConfig(
    require_outgoing_links=True,
    min_outgoing_links=10  # Require at least 10 outgoing links
)
```

#### Incoming Links (Target Page)  
Ensures the target page has sufficient backlinks (making it reachable):

```python
config = LinkValidationConfig(
    require_incoming_links=True,
    min_incoming_links=5  # Require at least 5 incoming links
)
```

#### Both Validations
For maximum game viability:

```python
config = LinkValidationConfig(
    require_outgoing_links=True,
    require_incoming_links=True,
    min_outgoing_links=5,
    min_incoming_links=3
)
```

### Performance Impact

Link validation adds API calls, impacting performance:

- **No validation**: ~0.5-1s (fastest)
- **Outgoing links only**: ~2-4s (uses wikipedia-api library)
- **Incoming links only**: ~1-2s (uses direct API calls)
- **Both validations**: ~3-6s (combines both approaches)

The system automatically optimizes by:
- Batching random page requests
- Using efficient API endpoints
- Skipping validation when disabled
- Caching Wikipedia API sessions

### Implementation Details

#### Outgoing Links Detection
Uses the `wikipedia-api` library to fetch page links:

```python
page = wiki_session.page(page_title)
outgoing_links = list(page.links.keys())
```

#### Incoming Links Detection  
Uses Wikipedia's backlinks API directly:

```python
params = {
    "action": "query",
    "list": "backlinks", 
    "bltitle": page_title,
    "blnamespace": "0"  # Main namespace only
}
```

### Usage Examples

#### Game with Guaranteed Navigation Options
```python
# Ensure players always have multiple navigation choices
config = LinkValidationConfig(
    require_outgoing_links=True,
    min_outgoing_links=10
)
page_pair = get_random_page_pair(link_validation=config)
```

#### Popular Target Pages Only
```python  
# Only target pages that are well-connected
config = LinkValidationConfig(
    require_incoming_links=True,
    min_incoming_links=20  # Popular pages only
)
page_pair = get_random_page_pair(link_validation=config)
```

#### Balanced Game Difficulty
```python
# Moderate requirements for balanced gameplay
config = LinkValidationConfig(
    require_outgoing_links=True,
    require_incoming_links=True,
    min_outgoing_links=5,    # Enough navigation options
    min_incoming_links=3     # Reachable but not too easy
)
```

### Error Handling

Link validation includes robust error handling:

- **API failures**: Falls back gracefully, continues without validation
- **Network timeouts**: Configurable timeout with retry logic  
- **Missing pages**: Automatically filters out non-existent pages
- **Rate limiting**: Respects Wikipedia API rate limits 