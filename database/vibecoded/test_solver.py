"""
Test script for the Wikipedia solver with a minimal dataset.

This creates a small test graph and verifies the pathfinding works correctly.
"""

import asyncio
import logging
from backend.services.wiki_db_service import wiki_db
from backend.services.wiki_solver_service import wiki_solver

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_test_data():
    """Create a small test graph for verification."""
    
    # Initialize the database
    await wiki_db.initialize_schema()
    
    # Create test pages
    pages = [
        "Python (programming language)",
        "Machine learning", 
        "Artificial intelligence",
        "Computer science",
        "Mathematics",
        "Science"
    ]
    
    for page in pages:
        await wiki_db.insert_page(page)
    
    # Create test links to form a path
    links = [
        ("Python (programming language)", "Machine learning"),
        ("Python (programming language)", "Computer science"),
        ("Machine learning", "Artificial intelligence"),
        ("Machine learning", "Mathematics"),
        ("Artificial intelligence", "Computer science"),
        ("Computer science", "Mathematics"),
        ("Computer science", "Science"),
        ("Mathematics", "Science")
    ]
    
    for source, target in links:
        await wiki_db.insert_link(source, target)
    
    logger.info(f"Created test data with {len(pages)} pages and {len(links)} links")

async def test_pathfinding():
    """Test the pathfinding algorithm."""
    
    await wiki_solver.initialize()
    
    # Test cases
    test_cases = [
        ("Python (programming language)", "Science"),
        ("Machine learning", "Science"),
        ("Python (programming language)", "Artificial intelligence"),
    ]
    
    for start, target in test_cases:
        try:
            result = await wiki_solver.find_shortest_path(start, target)
            logger.info(f"Path from '{start}' to '{target}':")
            logger.info(f"  Steps: {result.path_length}")
            logger.info(f"  Path: {' -> '.join(result.path)}")
            logger.info(f"  Time: {result.computation_time_ms:.1f}ms")
            logger.info(f"  From cache: {result.from_cache}")
            print()
        except Exception as e:
            logger.error(f"Failed to find path from '{start}' to '{target}': {e}")

async def test_cache():
    """Test that caching works correctly."""
    
    start, target = "Python (programming language)", "Science"
    
    # Clear any existing cache
    wiki_solver._path_cache.clear()
    
    # First query (should not be cached)
    result1 = await wiki_solver.find_shortest_path(start, target)
    logger.info(f"First query: {result1.computation_time_ms:.1f}ms, cached: {result1.from_cache}")
    
    # Second query (should be cached)
    result2 = await wiki_solver.find_shortest_path(start, target)
    logger.info(f"Second query: {result2.computation_time_ms:.1f}ms, cached: {result2.from_cache}")
    
    assert result1.path == result2.path
    assert not result1.from_cache
    assert result2.from_cache
    
    logger.info("Cache test passed!")

async def main():
    """Run all tests."""
    
    logger.info("Creating test data...")
    await create_test_data()
    
    logger.info("Testing pathfinding...")
    await test_pathfinding()
    
    logger.info("Testing cache...")
    await test_cache()
    
    # Show database stats
    page_count, link_count = await wiki_db.get_database_stats()
    logger.info(f"Database contains {page_count} pages and {link_count} links")
    
    # Show cache stats
    cache_stats = wiki_solver.get_cache_stats()
    logger.info(f"Cache stats: {cache_stats}")
    
    logger.info("All tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(main()) 