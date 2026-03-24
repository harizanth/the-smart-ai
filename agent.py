from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import (
    noise_cancellation,
)
from livekit.plugins import google
import logging
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web, send_email, get_youtube_channel_stats, get_youtube_top_videos, get_youtube_analytics, get_calendar_events, find_free_slots, create_calendar_event
load_dotenv(override=True)

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("livekit").setLevel(logging.DEBUG)

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
            voice="Aoede",
            temperature=0.8,
        ),
            tools=[
                get_weather,
                search_web,
                send_email,
                get_youtube_channel_stats,
                get_youtube_top_videos,
                get_youtube_analytics,
                get_calendar_events,
                find_free_slots,
                create_calendar_event,
            ],

        )
        


async def entrypoint(ctx: agents.JobContext):
    session = AgentSession(
        # ── Latency tuning ──────────────────────────────────────────────────
        min_endpointing_delay=0.2,
        max_endpointing_delay=2.0,
        preemptive_generation=True,
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    print("Connecting to room...")
    await ctx.connect()

    print("Agent connected. Generating initial greeting...")

    await session.generate_reply(
        instructions=SESSION_INSTRUCTION,
    )

    print("Greeting generated. Waiting for user input...")

    # Pre-warm the calendar cache in the background so Jarvis is ready instantly
    import asyncio as _asyncio
    from tools import prefetch_calendar_cache
    _asyncio.ensure_future(prefetch_calendar_cache())

    # Shutdown callback must be async; a plain lambda returns None which LiveKit tries to await
    async def _on_shutdown():
        print("Shutting down...")

    ctx.add_shutdown_callback(_on_shutdown)


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))