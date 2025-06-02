#!/usr/bin/env python3
"""
Test script for Wikipedia path finder using random page pairs.
Integrates page_selector.py with path_finder.py to test performance on random games.
"""
import asyncio
import sys
import time
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from pathlib import Path

# Add the wiki_arena directory to path to import page_selector
sys.path.append(str(Path(__file__).parent.parent / "wiki_arena"))

from path_finder import WikipediaPathFinder
from wikipedia.page_selector import WikipediaPageSelector, LinkValidationConfig

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)


@dataclass
class GameResult:
    """Results from a single game."""
    start_page: str
    target_page: str
    path: Optional[List[str]]
    duration: float
    success: bool
    path_length: Optional[int] = None
    
    def __post_init__(self):
        if self.path:
            self.path_length = len(self.path)


class RandomGameTester:
    """Tests Wikipedia path finder with random page pairs."""
    
    def __init__(self, num_games: int = 10, enable_link_validation: bool = True):
        self.num_games = num_games
        self.page_selector = WikipediaPageSelector(
            language="en",
            max_retries=3,
            link_validation=LinkValidationConfig(
                require_outgoing_links=enable_link_validation,
                require_incoming_links=enable_link_validation
            )
        )
        self.results: List[GameResult] = []
    
    async def run_tests(self) -> List[GameResult]:
        """Run all test games and return results."""
        logger.info(f"🎮 Starting {self.num_games} random Wikipedia path finding games...")
        print(f"🎮 Testing {self.num_games} random Wikipedia page pairs")
        print("=" * 60)
        
        async with WikipediaPathFinder() as path_finder:
            for game_num in range(1, self.num_games + 1):
                await self._run_single_game(game_num, path_finder)
        
        return self.results
    
    async def _run_single_game(self, game_num: int, path_finder: WikipediaPathFinder):
        """Run a single game."""
        print(f"\n🎯 Game {game_num}/{self.num_games}")
        print("-" * 40)
        
        # Get random page pair
        print("🎲 Selecting random page pair...")
        try:
            page_pair = await self.page_selector.select_page_pair_async()
            if not page_pair:
                print("❌ Failed to get valid page pair")
                return
            
            print(f"📖 Start: '{page_pair.start_page}'")
            print(f"🎯 Target: '{page_pair.target_page}'")
            
        except Exception as e:
            print(f"❌ Error selecting pages: {e}")
            return
        
        # Find path
        print("🔍 Finding path...")
        start_time = time.time()
        
        try:
            path = await path_finder.find_path(page_pair.start_page, page_pair.target_page)
            duration = time.time() - start_time
            
            # Record result
            result = GameResult(
                start_page=page_pair.start_page,
                target_page=page_pair.target_page,
                path=path,
                duration=duration,
                success=path is not None
            )
            self.results.append(result)
            
            # Display result
            if path:
                print(f"✅ Success in {duration:.2f}s!")
                print(f"📏 Path length: {len(path)} pages")
                print(f"🔗 Path: {' → '.join(path)}")
            else:
                print(f"❌ No path found ({duration:.2f}s)")
                
        except Exception as e:
            duration = time.time() - start_time
            print(f"❌ Error finding path: {e} ({duration:.2f}s)")
            
            result = GameResult(
                start_page=page_pair.start_page,
                target_page=page_pair.target_page,
                path=None,
                duration=duration,
                success=False
            )
            self.results.append(result)
    
    def print_summary(self):
        """Print summary statistics."""
        if not self.results:
            print("\n❌ No results to summarize")
            return
        
        print(f"\n{'='*60}")
        print("📊 TEST SUMMARY")
        print(f"{'='*60}")
        
        # Basic stats
        total_games = len(self.results)
        successful_games = sum(1 for r in self.results if r.success)
        success_rate = (successful_games / total_games) * 100 if total_games > 0 else 0
        
        print(f"🎮 Total games: {total_games}")
        print(f"✅ Successful: {successful_games}")
        print(f"❌ Failed: {total_games - successful_games}")
        print(f"📈 Success rate: {success_rate:.1f}%")
        
        # Timing stats
        durations = [r.duration for r in self.results]
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        
        print(f"\n⏱️  TIMING:")
        print(f"   Average: {avg_duration:.2f}s")
        print(f"   Fastest: {min_duration:.2f}s")
        print(f"   Slowest: {max_duration:.2f}s")
        print(f"   Total: {sum(durations):.2f}s")
        
        # Path length stats (for successful games)
        successful_results = [r for r in self.results if r.success and r.path_length]
        if successful_results:
            path_lengths = [r.path_length for r in successful_results]
            avg_path_length = sum(path_lengths) / len(path_lengths)
            min_path_length = min(path_lengths)
            max_path_length = max(path_lengths)
            
            print(f"\n🔗 PATH LENGTHS (successful games):")
            print(f"   Average: {avg_path_length:.1f} pages")
            print(f"   Shortest: {min_path_length} pages")
            print(f"   Longest: {max_path_length} pages")
        
        # Individual results
        print(f"\n📋 INDIVIDUAL RESULTS:")
        for i, result in enumerate(self.results, 1):
            status = "✅" if result.success else "❌"
            path_info = f"({result.path_length} pages)" if result.path_length else ""
            print(f"   {i:2d}. {status} {result.start_page} → {result.target_page} "
                  f"({result.duration:.2f}s) {path_info}")


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Wikipedia path finder with random page pairs")
    parser.add_argument("--games", "-n", type=int, default=10,
                        help="Number of games to test (default: 10)")
    parser.add_argument("--no-validation", action="store_true",
                        help="Disable link validation for faster page selection")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Reduce output verbosity")
    
    args = parser.parse_args()
    
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    # Run tests
    tester = RandomGameTester(
        num_games=args.games,
        enable_link_validation=not args.no_validation
    )
    
    start_time = time.time()
    
    try:
        results = await tester.run_tests()
        total_time = time.time() - start_time
        
        tester.print_summary()
        print(f"\n🏁 Total test time: {total_time:.2f}s")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        if tester.results:
            tester.print_summary()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0) 