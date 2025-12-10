from pathlib import Path

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth

from config import config_data, get_app_config

SCOPES = [
    "user-read-currently-playing",
    "user-read-playback-state",
]
OPEN_BROWSER = True

if __name__ == "__main__":
    app_config = get_app_config()
    store_dir = app_config["store_dir"]

    spofity_config = config_data.get("tasks", {}).get("spotify_current_playback", {})
    client_id = spofity_config.get("client_id", "")
    client_secret = spofity_config.get("client_secret", "")
    redirect_uri = spofity_config.get("redirect_uri", "http://127.0.0.1:1234")
    auth_cache_file = spofity_config.get("auth_cache_file", "spotify_cache.json")
    cache_path = str(Path(__file__).parent / store_dir / auth_cache_file)

    if not client_id or not client_secret or not redirect_uri or not auth_cache_file:
        raise Exception("Spotify configuration incomplete in config.yaml")

    sp = spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=SCOPES,
            open_browser=OPEN_BROWSER,
            cache_handler=CacheFileHandler(cache_path=cache_path),
        )
    )

    res = sp.me()
    print(res)
