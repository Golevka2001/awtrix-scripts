from .task_air_quality import AirQualityTask
from .task_bilibili_followers import BilibiliFollowersTask
from .task_gas_price import GasPriceTask
from .task_github_followers import GithubFollowersTask
from .task_minecraft_server_status import MinecraftServerStatusTask
from .task_spotify_current_playback import SpotifyCurrentPlaybackTask
from .task_year_progress import YearProgressTask


def load_tasks():
    tasks = [
        AirQualityTask(),
        BilibiliFollowersTask(),
        GasPriceTask(),
        GithubFollowersTask(),
        MinecraftServerStatusTask(),
        SpotifyCurrentPlaybackTask(),
        YearProgressTask(),
    ]
    return sorted(tasks, key=lambda t: t.priority)
