from pathlib import Path

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth

from config import STORE_DIR, config_data
from helpers import cjk_to_initials, fetch_image_and_convert_to_base64

from .base import BaseTask

ICON = "48861"
TEXT_GRADIENT = ["1dd760", "ffffff"]
SCROLL_SPEED = 40
PROGRESS_COLOR = "#ffffff"
PROGRESS_BG_COLOR = "#666666"

ERROR_ICON = ICON

# https://developer.spotify.com/documentation/web-api/reference/get-the-users-currently-playing-track
SPOTIFY_SCOPES = [
    "user-read-currently-playing",
    "user-read-playback-state",
]

APP_NAME = "spotify_current_playback"
DEFAULT_INTERVAL = 10


class SpotifyCurrentPlaybackTask(BaseTask):
    """Spotify current playback"""

    def __init__(self):
        super().__init__(APP_NAME, default_interval=DEFAULT_INTERVAL)

    def fetch_data(self):
        """Fetch Spotify current playback data"""
        task_config = config_data.get("tasks", {}).get(APP_NAME, {})
        client_id = task_config.get("client_id")
        client_secret = task_config.get("client_secret")
        redirect_uri = task_config.get("redirect_uri", "http://127.0.0.1:1234")
        auth_cache_file = task_config.get("auth_cache_file", "spotify_cache.json")
        cache_path = str(Path(STORE_DIR) / auth_cache_file)
        self.show_artist = task_config.get("show_artist", True)
        self.track_name_first = task_config.get("track_name_first", True)
        self.cjk_to_initials = task_config.get("cjk_to_initials", True)
        self.draw_album_art = task_config.get("draw_album_art", False)

        if not auth_cache_file:
            raise Exception("Spotify auth_cache_file not configured")

        self.sp = spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=SPOTIFY_SCOPES,
                open_browser=False,
                cache_handler=CacheFileHandler(cache_path=cache_path),
            )
        )

        data = self.sp.current_playback()
        return data

    def create_mqtt_message(self, data):
        """Create MQTT message from current playback data"""
        # No playback
        if not data:
            return {}

        is_playing = data.get("is_playing", False)
        if not is_playing:
            return {}

        item = data.get("item", {})
        if not item:
            return {}

        # Text info
        track_name = item.get("name", "Unknown")
        if self.show_artist:
            artist = item.get("artists", [{}])[0].get("name", "Unknown")
            if self.track_name_first:
                track_display = f"{track_name} - {artist}"
            else:
                track_display = f"{artist} - {track_name}"
        else:
            track_display = track_name

        # Convert CJK characters to initials
        if self.cjk_to_initials:
            track_display = cjk_to_initials(track_display)

        # Playback progress
        progress_ms = data.get("progress_ms", 0)
        duration_ms = item.get("duration_ms", 1)  # Avoid division by zero
        progress_percent = int(round((progress_ms / duration_ms) * 100))

        # Use album art as icon if enabled
        icon = ICON
        if self.draw_album_art:
            album_art_url = item.get("album", {}).get("images", [{}])[-1].get("url", "")
            icon = (
                fetch_image_and_convert_to_base64(
                    album_art_url, (8, 8), image_format="JPG"
                )
                or ICON
            )

        return {
            "icon": icon,
            "textCase": 2,
            "text": track_display,
            "gradient": TEXT_GRADIENT,
            "scrollSpeed": SCROLL_SPEED,
            "progress": progress_percent,
            "progressC": PROGRESS_COLOR,
            "progressBC": PROGRESS_BG_COLOR,
        }

    def get_error_message(self):
        return {
            "icon": ERROR_ICON,
            "textCase": 2,
            "text": "Error",
            "color": "#666666",
        }


if __name__ == "__main__":
    # uv run -m tasks.task_spotify_current_playback
    import json
    import sys

    from mqtt_sender import send_message

    task = SpotifyCurrentPlaybackTask()

    if len(sys.argv) > 1 and sys.argv[1] == "del":
        print("Deleting app...")
        send_message(task.name, "{}")
        exit()

    try:
        data = task.fetch_data()
        msg = task.create_mqtt_message(data)
    except Exception as e:
        print("Error:", e)
        msg = task.get_error_message()

    msg = json.dumps(msg)
    print(msg)

    send_message(task.name, msg)
