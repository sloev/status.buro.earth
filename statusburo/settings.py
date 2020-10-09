from os import environ

DB_FILE = "data/statusburo.db"
SPOTIFY_CALLBACK_URL = environ.get(
    "SPOTIFY_CALLBACK_URL", "http://127.0.0.1:9002/spotify/create"
)
SPOTIFY_CLIENT_ID = environ["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET = environ["SPOTIFY_CLIENT_SECRET"]
SPOTIFY_CRON_INTERVAL_SECONDS = int(environ.get("SPOTIFY_CRON_INTERVAL_SECONDS", 10))
SPOTIFY_MINUTES_BETWEEN_REFRESH = int(
    environ.get("SPOTIFY_MINUTES_BETWEEN_REFRESH", 10)
)
SPOTIFY_COOKIE_NAME = "statusburo.spotify"
TESTING = int(environ.get("TESTING", 0))
