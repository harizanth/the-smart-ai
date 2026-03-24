import asyncio
import os
from dotenv import load_dotenv
from tools import get_calendar_events, find_free_slots, create_calendar_event

load_dotenv(override=True)

async def test_calendar():
    print("Testing Google Calendar Integration...\n")

    print("1. Today's events...")
    events = await get_calendar_events(None)
    print(events)
    print("-" * 50)

    print("\n2. Finding free 60-min slots today...")
    slots = await find_free_slots(None, duration_minutes=60)
    print(slots)
    print("-" * 50)

    print("\nTests completed.")

if __name__ == "__main__":
    asyncio.run(test_calendar())
