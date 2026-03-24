import asyncio
import os
from dotenv import load_dotenv
from tools import get_youtube_channel_stats, get_youtube_top_videos, get_youtube_analytics

# Load environment variables
load_dotenv(override=True)

async def test_youtube_tools():
    print("Testing YouTube Integration Tools...\n")
    
    print("1. Testing Channel Stats...")
    stats = await get_youtube_channel_stats(None)
    print(stats)
    print("-" * 50)
    
    print("\n2. Testing Top Videos...")
    top_videos = await get_youtube_top_videos(None, max_results=3)
    print(top_videos)
    print("-" * 50)
    
    print("\n3. Testing Analytics (Last 30 Days)...")
    analytics = await get_youtube_analytics(None, days_back=30)
    print(analytics)
    print("-" * 50)
    
    print("\nTests completed.")

if __name__ == "__main__":
    # Ensure there is a dummy context for the function calls
    asyncio.run(test_youtube_tools())
