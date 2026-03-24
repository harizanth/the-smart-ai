import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Scopes required for YouTube Data API and YouTube Analytics API
SCOPES = [
    'https://www.googleapis.com/auth/yt-analytics.readonly',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
]

def get_youtube_credentials():
    """
    Handles the OAuth 2.0 flow to get credentials for YouTube APIs.
    Reads from token.pickle if available and valid, otherwise prompts user
    to login via browser using client_secret.json.
    """
    creds = None
    token_file = 'token.pickle'
    client_secret_file = 'client_secret.json'

    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(client_secret_file):
                raise FileNotFoundError(
                    f"Missing '{client_secret_file}'. Please download it from Google Cloud Console "
                    "after setting up OAuth 2.0 for a Desktop App."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secret_file, SCOPES)
            # Run local server to capture the authorization code
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)

    return creds

# Module-level cache — built once per process, reused on every subsequent call
_youtube_data = None
_youtube_analytics = None
_google_calendar = None

def get_youtube_services():
    """
    Returns the initialized YouTube Data API and YouTube Analytics API services.
    Clients are cached at module level so the expensive discovery build()
    only happens once per process lifetime.
    """
    global _youtube_data, _youtube_analytics
    if _youtube_data is None or _youtube_analytics is None:
        creds = get_youtube_credentials()
        _youtube_data = build('youtube', 'v3', credentials=creds)
        _youtube_analytics = build('youtubeAnalytics', 'v2', credentials=creds)
    return _youtube_data, _youtube_analytics

def get_calendar_service():
    """
    Returns the initialized Google Calendar API service.
    Reuses the same OAuth credentials as YouTube. Cached after first call.
    """
    global _google_calendar
    if _google_calendar is None:
        creds = get_youtube_credentials()
        _google_calendar = build('calendar', 'v3', credentials=creds)
    return _google_calendar

if __name__ == '__main__':
    # Test getting credentials
    print("Testing YouTube Authentication...")
    try:
        data, analytics = get_youtube_services()
        print("Successfully authenticated and initialized YouTube services!")
        
        # Test a simple query to get the user's channel ID
        request = data.channels().list(mine=True, part='id,snippet')
        response = request.execute()
        
        if 'items' in response and len(response['items']) > 0:
            channel = response['items'][0]
            print(f"Authenticated as channel: {channel['snippet']['title']} (ID: {channel['id']})")
        else:
            print("No channel found for the authenticated user.")
            
    except Exception as e:
        print(f"Authentication failed: {e}")
