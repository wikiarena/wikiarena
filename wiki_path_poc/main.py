"""
CLI interface for Wikipedia path finding POC.
Usage: python main.py <start_page> <target_page>
"""
import asyncio
import sys
import time
import logging
from path_finder import WikipediaPathFinder

# Set up nice logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

def print_usage():
    """Print usage instructions."""
    print("Wikipedia Path Finder POC")
    print("=" * 40)
    print("Usage: python main.py <start_page> <target_page>")
    print("")
    print("Examples:")
    print("  python main.py 'Python' 'Java'")
    print("  python main.py 'Barack Obama' 'Donald Trump'")
    print("  python main.py 'USA' 'Canada'")
    print("")
    print("Note: Page titles are case-sensitive but redirects are handled automatically")


async def find_and_display_path(start: str, target: str):
    """Find path and display results nicely."""
    print(f"\n🔍 Searching for path from '{start}' to '{target}'...")
    print("-" * 60)
    
    start_time = time.time()
    
    async with WikipediaPathFinder() as finder:
        path = await finder.find_path(start, target)
        
        elapsed = time.time() - start_time
        
        if path:
            print(f"\n✅ Path found in {elapsed:.2f} seconds!")
            print(f"📏 Path length: {len(path)} pages")
            print(f"🔗 Path:")
            print()
            
            for i, page in enumerate(path):
                if i == 0:
                    print(f"   🏁 {page}")
                elif i == len(path) - 1:
                    print(f"   🎯 {page}")
                else:
                    print(f"   📄 {page}")
                    
                if i < len(path) - 1:
                    print("   ⬇")
            
            print(f"\n📊 Cache Statistics:")
            cache_stats = finder.cache.get_cache_stats()
            for key, value in cache_stats.items():
                if key == "current_target":
                    print(f"   {key}: '{value}'")
                else:
                    print(f"   {key}: {value:,}")
                    
        else:
            print(f"\n❌ No path found after {elapsed:.2f} seconds")
            print("   This could mean:")
            print("   - Pages are in different Wikipedia language editions")
            print("   - One of the pages doesn't exist")
            print("   - Path requires more than 10 hops (algorithm limit)")
            print("   - Search was limited to avoid overloading Wikipedia")


async def interactive_mode():
    """Run in interactive mode for testing multiple paths."""
    print("🚀 Wikipedia Path Finder - Interactive Mode")
    print("=" * 50)
    print("Enter page pairs to find paths between them.")
    print("Type 'quit' or 'exit' to stop.")
    print("")
    
    async with WikipediaPathFinder() as finder:
        while True:
            try:
                print("\n" + "-" * 50)
                start = input("Start page: ").strip()
                if start.lower() in ['quit', 'exit', '']:
                    break
                    
                target = input("Target page: ").strip()
                if target.lower() in ['quit', 'exit', '']:
                    break
                
                if not start or not target:
                    print("❌ Please enter both start and target pages")
                    continue
                
                start_time = time.time()
                path = await finder.find_path(start, target)
                elapsed = time.time() - start_time
                
                if path:
                    print(f"\n✅ Path found in {elapsed:.2f}s: {' → '.join(path)}")
                    print(f"📏 Length: {len(path)} pages")
                else:
                    print(f"\n❌ No path found after {elapsed:.2f}s")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")


async def test_game_continuation():
    """Test the game continuation scenario (same target, different starts)."""
    print("🎮 Testing Game Continuation Scenario")
    print("=" * 50)
    print("This simulates a game where the target stays the same")
    print("but the start page changes (like in your wiki arena).")
    print()
    
    target = "United States"
    start_pages = ["Python (programming language)", "Barack Obama", "Germany", "Mathematics"]
    
    async with WikipediaPathFinder() as finder:
        for i, start in enumerate(start_pages):
            print(f"\n🔄 Round {i+1}: Finding path from '{start}' to '{target}'")
            
            start_time = time.time()
            path = await finder.find_path(start, target)
            elapsed = time.time() - start_time
            
            if path:
                print(f"   ✅ Found in {elapsed:.2f}s: {len(path)} pages")
                print(f"   📍 Path: {' → '.join(path)}")
            else:
                print(f"   ❌ No path found in {elapsed:.2f}s")
            
            # Show cache benefits
            cache_stats = finder.cache.get_cache_stats()
            print(f"   💾 Cache: {cache_stats['total_pages']} pages, "
                  f"{cache_stats['total_outgoing_links'] + cache_stats['total_incoming_links']:,} links")


async def main():
    """Main entry point."""
    if len(sys.argv) == 1:
        # No arguments - show menu
        print("Wikipedia Path Finder POC")
        print("=" * 30)
        print("1. Find single path")
        print("2. Interactive mode") 
        print("3. Test game continuation")
        print("4. Show usage")
        print()
        
        choice = input("Choose option (1-4): ").strip()
        
        if choice == "1":
            start = input("Start page: ").strip()
            target = input("Target page: ").strip()
            if start and target:
                await find_and_display_path(start, target)
            else:
                print("❌ Please enter both pages")
                
        elif choice == "2":
            await interactive_mode()
            
        elif choice == "3":
            await test_game_continuation()
            
        elif choice == "4":
            print_usage()
            
        else:
            print("❌ Invalid choice")
            
    elif len(sys.argv) == 3:
        # Command line arguments provided
        start = sys.argv[1]
        target = sys.argv[2]
        await find_and_display_path(start, target)
        
    else:
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1) 