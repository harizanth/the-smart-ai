import logging
from livekit.agents import function_tool, RunContext
import requests
from langchain_community.tools import DuckDuckGoSearchRun
import os
import smtplib
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
from typing import Optional

@function_tool()
async def get_weather(
    context: RunContext,  # type: ignore
    city: str) -> str:
    """
    Get the current weather for a given city.
    
    Args:
        city: The name of the city to get the weather for. Example: 'Seattle', 'New York'
    """
    try:
        # First, get the coordinates for the city
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
        geo_response = requests.get(geo_url, timeout=10)
        if geo_response.status_code != 200 or not geo_response.json().get("results"):
            return f"Could not find coordinates for {city}."
            
        location = geo_response.json()["results"][0]
        lat, lon = location["latitude"], location["longitude"]
        
        # Then, get the weather
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        response = requests.get(weather_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json().get("current_weather", {})
            temp = data.get("temperature", "unknown")
            windspeed = data.get("windspeed", "unknown")
            result = f"The current weather in {city} is {temp}°C with {windspeed} km/h wind."
            logging.info(result)
            return result
        else:
            logging.error(f"Failed to get weather for {city}: {response.status_code}")
            return f"Could not retrieve weather for {city}."
    except Exception as e:
        logging.error(f"Error retrieving weather for {city}: {e}")
        return f"An error occurred while retrieving weather for {city}." 

@function_tool()
async def search_web(
    context: RunContext,  # type: ignore
    query: str) -> str:
    """
    Search the web using DuckDuckGo.
    
    Args:
        query: The search query to look up on the web. Example: 'President of the USA'
    """
    try:
        results = DuckDuckGoSearchRun().run(tool_input=query)
        logging.info(f"Search results for '{query}': {results}")
        return results
    except Exception as e:
        logging.error(f"Error searching the web for '{query}': {e}")
        return f"An error occurred while searching the web for '{query}'."    

@function_tool()    
async def send_email(
    context: RunContext,  # type: ignore
    to_email: str,
    subject: str,
    message: str
) -> str:
    """
    Send an email through Gmail.
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        message: Email body content
    """
    try:
        # Gmail SMTP configuration
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        
        # Get credentials from environment variables
        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")  # Use App Password, not regular password
        
        if not gmail_user or not gmail_password:
            logging.error("Gmail credentials not found in environment variables")
            return "Email sending failed: Gmail credentials not configured."
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to_email
        msg['Subject'] = subject
        
        recipients = [to_email]
        
        # Attach message body
        msg.attach(MIMEText(message, 'plain'))
        
        # Connect to Gmail SMTP server
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Enable TLS encryption
        server.login(gmail_user, gmail_password)
        
        # Send email
        text = msg.as_string()
        server.sendmail(gmail_user, recipients, text)
        server.quit()
        
        logging.info(f"Email sent successfully to {to_email}")
        return f"Email sent successfully to {to_email}"
        
    except smtplib.SMTPAuthenticationError:
        logging.error("Gmail authentication failed")
        return "Email sending failed: Authentication error. Please check your Gmail credentials."
    except smtplib.SMTPException as e:
        logging.error(f"SMTP error occurred: {e}")
        return f"Email sending failed: SMTP error - {str(e)}"
    except Exception as e:
        logging.error(f"Error sending email: {e}")
        return f"An error occurred while sending email: {str(e)}"

# YouTube Integration Tools
from youtube_auth import get_youtube_services, get_calendar_service
from datetime import datetime, timedelta
import pytz

# ─── User's personal daily schedule blocks (IST) ─────────────────────────────
# Jarvis will never suggest slots that overlap with these windows.
_BLOCKED_WINDOWS = [
    ("00:00", "07:00"),  # Sleep
    ("07:00", "08:00"),  # Breakfast
    ("13:00", "14:00"),  # Lunch
    ("20:00", "21:00"),  # Dinner
    ("23:00", "23:59"),  # Wind-down / sleep
]
_USER_TZ = pytz.timezone("Asia/Kolkata")

# ─── Calendar cache: background prefetch, max 2 entries, auto-evict past ─────
import time as _time
import asyncio as _asyncio

_calendar_cache: dict[str, tuple[float, list]] = {}   # date_str -> (fetched_at, events)
_PREFETCH_INTERVAL = 300   # refresh every 5 min (well within API quota)
_MAX_CACHE_ENTRIES = 2     # only keep today + tomorrow

def _evict_old_cache():
    """Keep only the 2 most-recent date keys; drop anything in the past."""
    today = datetime.now(_USER_TZ).strftime("%Y-%m-%d")
    # Remove keys strictly before today
    past_keys = [k for k in list(_calendar_cache.keys()) if k < today]
    for k in past_keys:
        _calendar_cache.pop(k, None)
    # If still too many, drop the oldest by fetch time
    if len(_calendar_cache) > _MAX_CACHE_ENTRIES:
        sorted_keys = sorted(_calendar_cache.keys(), key=lambda k: _calendar_cache[k][0])
        for k in sorted_keys[:len(_calendar_cache) - _MAX_CACHE_ENTRIES]:
            _calendar_cache.pop(k, None)

def _fetch_events_for_day(svc, date_key: str) -> list:
    """Synchronously fetch events for a date from Google Calendar and store in cache."""
    tz = _USER_TZ
    day = datetime.strptime(date_key, "%Y-%m-%d").replace(tzinfo=tz)
    start = day.isoformat()
    end = (day + timedelta(days=1)).isoformat()
    result = svc.events().list(
        calendarId='primary',
        timeMin=start,
        timeMax=end,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = result.get('items', [])
    _calendar_cache[date_key] = (_time.time(), events)
    logging.info(f"[CalCache] Fetched {len(events)} events for {date_key}")
    _evict_old_cache()
    return events

async def prefetch_calendar_cache():
    """
    Background task: pre-warm today + tomorrow on startup, then refresh every
    5 minutes. Call this once per agent session via asyncio.ensure_future().
    """
    import concurrent.futures
    loop = _asyncio.get_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    async def _refresh():
        try:
            svc = get_calendar_service()
            tz = _USER_TZ
            today = datetime.now(tz).strftime("%Y-%m-%d")
            tomorrow = (datetime.now(tz) + timedelta(days=1)).strftime("%Y-%m-%d")
            for date_key in [today, tomorrow]:
                await loop.run_in_executor(executor, _fetch_events_for_day, svc, date_key)
        except Exception as e:
            logging.warning(f"[CalCache] Background prefetch failed: {e}")

    # Initial warm-up — runs immediately so first query is always a cache hit
    await _refresh()

    # Keep refreshing on schedule
    while True:
        await _asyncio.sleep(_PREFETCH_INTERVAL)
        await _refresh()

def _get_cached_events(svc, date_key: str, day) -> list:
    """Return calendar events for a date. If fresh cache exists, instant. Otherwise fetch."""
    cached = _calendar_cache.get(date_key)
    if cached:
        return cached[1]  # always instant if prefetch did its job
    # Fallback: synchronous fetch (only happens if date hasn't been prefetched)
    return _fetch_events_for_day(svc, date_key)


@function_tool()
async def get_youtube_channel_stats(
    context: RunContext,  # type: ignore
    channel_id: Optional[str] = None
) -> str:
    """
    Get basic statistics for a YouTube channel such as subscribers, total views, and video count.
    
    Args:
        channel_id: Optional. The ID of the YouTube channel. If not provided, it will use the authenticated user's channel. Example: 'UC_x5XG1OV2P6uZZ5FSM9Ttw'
    """
    try:
        data_svc, _ = get_youtube_services()
        
        if not channel_id:
            channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
            
        if channel_id:
            request = data_svc.channels().list(part="statistics,snippet", id=channel_id)
        else:
             request = data_svc.channels().list(part="statistics,snippet", mine=True)
             
        response = request.execute()
        
        if 'items' not in response or not response['items']:
            return "Could not find the YouTube channel."
            
        channel = response['items'][0]
        title = channel['snippet']['title']
        stats = channel['statistics']
        
        subs = stats.get('subscriberCount', 'unknown')
        views = stats.get('viewCount', 'unknown')
        videos = stats.get('videoCount', 'unknown')
        
        result = f"Channel '{title}' has {subs} subscribers, {videos} videos, and {views} total views."
        logging.info(result)
        return result
    except Exception as e:
        logging.error(f"Error getting youtube stats: {e}")
        return f"An error occurred while fetching YouTube stats: {e}"

@function_tool()
async def get_youtube_top_videos(
    context: RunContext,  # type: ignore
    max_results: int = 3
) -> str:
    """
    Get the best-performing (most viewed) videos from the user's YouTube channel.
    
    Args:
         max_results: The number of top videos to return. Default is 3. Max is 10.
    """
    try:
        data_svc, _ = get_youtube_services()
        
        # First get the user's channel to find their uploads playlist
        request = data_svc.channels().list(part="contentDetails,snippet", mine=True)
        response = request.execute()
        
        if 'items' not in response or not response['items']:
            return "Could not find your YouTube channel."
            
        uploads_playlist_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        # Fetch only enough videos to find the top ones (2x buffer for sorting, capped at 10)
        fetch_count = min(max_results * 2, 10)
        playlist_ops = data_svc.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=fetch_count
        ).execute()
        
        if not playlist_ops.get('items'):
            return "Your channel has no uploaded videos."
            
        video_ids = [item['contentDetails']['videoId'] for item in playlist_ops['items']]
        
        # Now get the stats for these videos
        video_response = data_svc.videos().list(
            part="statistics,snippet",
            id=','.join(video_ids)
        ).execute()
        
        videos = []
        for v in video_response.get('items', []):
            title = v['snippet']['title']
            views = int(v['statistics'].get('viewCount', 0))
            videos.append({'title': title, 'views': views})
            
        # Sort by views descending
        videos.sort(key=lambda x: x['views'], reverse=True)
        top_videos = videos[:min(max_results, 10, len(videos))]
        
        result_lines = ["Here are your top performing videos:"]
        for i, v in enumerate(top_videos, 1):
            result_lines.append(f"{i}. {v['title']} with {v['views']} views")
            
        result = ". ".join(result_lines)
        logging.info(result)
        return result
        
    except Exception as e:
        logging.error(f"Error getting top videos: {e}")
        return f"An error occurred while fetching top videos: {e}"

@function_tool()
async def get_youtube_analytics(
    context: RunContext, # type: ignore
    days_back: int = 30
) -> str:
    """
    Get YouTube Analytics metrics (watch time, average view duration, views) for the recent past.
    
    Args:
        days_back: Number of days back to get analytics for. Default is 30.
    """
    try:
        _, analytics_svc = get_youtube_services()
        
        # YouTube analytics are usually delayed by 2 days
        end_date = (datetime.utcnow() - timedelta(days=2)).strftime('%Y-%m-%d')
        start_date = (datetime.utcnow() - timedelta(days=days_back + 2)).strftime('%Y-%m-%d')
        
        request = analytics_svc.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="estimatedMinutesWatched,averageViewDuration,views",
        )
        response = request.execute()
        
        if 'rows' not in response or not response['rows']:
            return f"No analytics data available for the last {days_back} days."
            
        # Summarize the data (since query is cumulative without dimensions)
        row = response['rows'][0]
        # order matches metrics: estimatedMinutesWatched, averageViewDuration, views
        watch_time = row[0]
        avg_view_dur = row[1] 
        views = row[2]
        
        result = (f"In the last {days_back} days, your channel received {views} views "
                  f"and {watch_time} minutes of watch time. Average view duration was {int(avg_view_dur)} seconds.")
        logging.info(result)
        return result
        
    except Exception as e:
        logging.error(f"Error getting analytics: {e}")
        return f"An error occurred while fetching analytics: {e}. Make sure you are authenticated with Analytics permissions."


# ─── Google Calendar Tools ────────────────────────────────────────────────────

@function_tool()
async def get_calendar_events(
    context: RunContext,  # type: ignore
    date: Optional[str] = None
) -> str:
    """
    Get the user's Google Calendar events for a specific date.

    Args:
        date: Date to fetch events for in YYYY-MM-DD format. Defaults to today if not provided.
    """
    try:
        svc = get_calendar_service()
        tz = _USER_TZ

        if date:
            day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=tz)
            date_key = date
        else:
            day = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
            date_key = day.strftime("%Y-%m-%d")

        events = _get_cached_events(svc, date_key, day)  # uses cache if fresh

        if not events:
            label = "today" if not date else date
            return f"You have no events scheduled for {label}."

        lines = []
        for e in events:
            title = e.get('summary', '(No title)')
            start_raw = e['start'].get('dateTime', e['start'].get('date'))
            end_raw = e['end'].get('dateTime', e['end'].get('date'))
            try:
                s = datetime.fromisoformat(start_raw).astimezone(tz).strftime("%-I:%M %p")
                en = datetime.fromisoformat(end_raw).astimezone(tz).strftime("%-I:%M %p")
                lines.append(f"• {title} from {s} to {en}")
            except Exception:
                lines.append(f"• {title} (all day)")

        label = "today" if not date else date
        return f"Here are your events for {label}:\n" + "\n".join(lines)

    except Exception as e:
        logging.error(f"Error fetching calendar events: {e}")
        return f"An error occurred while fetching calendar events: {e}"


@function_tool()
async def find_free_slots(
    context: RunContext,  # type: ignore
    date: Optional[str] = None,
    duration_minutes: int = 60
) -> str:
    """
    Find available time slots on a given date, respecting existing events and the user's personal schedule (sleep, meals).

    Args:
        date: Date to search in YYYY-MM-DD format. Defaults to today.
        duration_minutes: How long the meeting needs to be in minutes. Default is 60.
    """
    try:
        svc = get_calendar_service()
        tz = _USER_TZ

        if date:
            day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=tz)
            date_key = date
        else:
            day = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
            date_key = day.strftime("%Y-%m-%d")

        # Use cache for event lookup — instant on repeat queries
        cal_events = _get_cached_events(svc, date_key, day)

        busy = []
        for e in cal_events:
            s_raw = e['start'].get('dateTime')
            e_raw = e['end'].get('dateTime')
            if s_raw and e_raw:
                busy.append((
                    datetime.fromisoformat(s_raw).astimezone(tz),
                    datetime.fromisoformat(e_raw).astimezone(tz)
                ))

        # Add personal schedule blocks
        for (bs, be) in _BLOCKED_WINDOWS:
            bsh, bsm = map(int, bs.split(":"))
            beh, bem = map(int, be.split(":"))
            busy.append((
                day.replace(hour=bsh, minute=bsm, second=0),
                day.replace(hour=beh, minute=bem, second=0)
            ))

        busy.sort(key=lambda x: x[0])

        # Scan the day in 30-min increments for free windows
        delta = timedelta(minutes=duration_minutes)
        step = timedelta(minutes=30)
        cursor = day.replace(hour=8, minute=0, second=0)
        day_end = day.replace(hour=23, minute=0, second=0)

        free_slots = []
        while cursor + delta <= day_end and len(free_slots) < 5:
            slot_end = cursor + delta
            overlap = any(b[0] < slot_end and b[1] > cursor for b in busy)
            if not overlap:
                free_slots.append((cursor, slot_end))
                cursor = slot_end
            else:
                cursor += step

        if not free_slots:
            label = "today" if not date else date
            return f"I couldn't find any free {duration_minutes}-minute slots on {label}, your schedule is quite packed."

        label = "today" if not date else date
        lines = [f"Here are your free {duration_minutes}-minute windows on {label}:"]
        for (s, e) in free_slots:
            lines.append(f"• {s.strftime('%-I:%M %p')} – {e.strftime('%-I:%M %p')}")
        return "\n".join(lines)

    except Exception as e:
        logging.error(f"Error finding free slots: {e}")
        return f"An error occurred while finding free slots: {e}"


@function_tool()
async def create_calendar_event(
    context: RunContext,  # type: ignore
    title: str,
    date: str,
    start_time: str,
    end_time: str,
    description: Optional[str] = None
) -> str:
    """
    Create a new event in the user's primary Google Calendar.

    Args:
        title: Title/name of the event.
        date: Date of the event in YYYY-MM-DD format.
        start_time: Start time in HH:MM (24-hour) format. Example: '14:30'
        end_time: End time in HH:MM (24-hour) format. Example: '15:30'
        description: Optional description or notes for the event.
    """
    try:
        svc = get_calendar_service()
        tz_str = "Asia/Kolkata"

        start_dt = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")

        event_body = {
            'summary': title,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': tz_str},
            'end':   {'dateTime': end_dt.isoformat(),   'timeZone': tz_str},
        }
        if description:
            event_body['description'] = description

        created = svc.events().insert(calendarId='primary', body=event_body).execute()

        # Bust the cache for this date so the next event lookup is fresh
        _calendar_cache.pop(date, None)

        link = created.get('htmlLink', '')
        return f"Done! '{title}' has been added to your calendar on {date} from {start_time} to {end_time}. {link}"

    except Exception as e:
        logging.error(f"Error creating calendar event: {e}")
        return f"An error occurred while creating the calendar event: {e}"