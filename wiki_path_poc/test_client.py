"""
Test script for Wikipedia client.
Run this to verify API interactions work correctly.
"""
import asyncio
import logging
from wikipedia_client import WikipediaClient

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)


async def test_redirect_resolution():
    """Test that redirect resolution works correctly."""
    print("=== Testing Redirect Resolution ===")
    
    async with WikipediaClient() as client:
        test_titles = [
            "USA",  # Should redirect to "United States"
            "steve jobs",  # Should normalize/redirect to "Steve Jobs"  
            "Python",  # Should stay as "Python"
            "Barack Obama"  # Should stay as "Barack Obama"
        ]
        
        redirects = await client.resolve_redirects(test_titles)
        
        for original, canonical in redirects.items():
            print(f"'{original}' → '{canonical}'")


async def test_forward_links():
    """Test getting outgoing links from a page."""
    print("\n=== Testing Forward Links ===")
    
    async with WikipediaClient() as client:
        # Test with a simple page that has known links
        titles = ["Python (programming language)"]
        
        links = await client.get_forward_links(titles)
        
        for title, link_set in links.items():
            print(f"'{title}' links to {len(link_set)} pages")
            # Print first few links as examples
            for i, link in enumerate(sorted(link_set)):
                if i >= 5:  # Just show first 5
                    print(f"  ... and {len(link_set) - 5} more")
                    break
                print(f"  → {link}")


async def test_backward_links():
    """Test getting incoming links to a page."""
    print("\n=== Testing Backward Links ===")
    
    async with WikipediaClient() as client:
        # Test with a notable page that has many incoming links
        titles = ["Python (programming language)"]
        
        links = await client.get_backward_links(titles)
        
        for title, link_set in links.items():
            print(f"'{title}' is linked from {len(link_set)} pages")
            # Print first few links as examples
            for i, link in enumerate(sorted(link_set)):
                if i >= 5:  # Just show first 5
                    print(f"  ... and {len(link_set) - 5} more")
                    break
                print(f"  ← {link}")


async def test_batch_processing():
    """Test that batching works with multiple titles."""
    print("\n=== Testing Batch Processing ===")
    
    async with WikipediaClient() as client:
        # Test with multiple titles to verify batching works
        titles = [
            "Python (programming language)",
            "Java (programming language)", 
            "JavaScript",
            "C++",
            "Rust (programming language)"
        ]
        
        print(f"Getting forward links for {len(titles)} programming languages...")
        links = await client.get_forward_links(titles)
        
        for title, link_set in links.items():
            print(f"'{title}': {len(link_set)} outgoing links")


async def main():
    """Run all tests."""
    try:
        await test_redirect_resolution()
        await test_forward_links()
        await test_backward_links()
        await test_batch_processing()
        print("\n✅ All tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main()) 