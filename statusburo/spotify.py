import time
import asyncio
from statusburo import settings, utils, db, rendering, static
from urllib.parse import urlencode
from typing import NamedTuple
from sanic import Blueprint, response
import logging
import json
import os

SPOTIFY_INDEX_TEMPLATE = static.templates["spotify_index_html"]

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_URL = "https://api.spotify.com/v1"


async def get_latest_gif_wall(n):
    uuids = await db.singleton.spotify_get_latest_public(n)
    html = ""
    for uuid in uuids:
        html += f'<img class="gif-wall-item" src="/images/{uuid}.gif"/>'
    return html


def get_spotify_auth_link(state):
    params = urlencode(
        {
            "client_id": settings.SPOTIFY_CLIENT_ID,
            "scope": "user-read-recently-played",
            "redirect_uri": settings.SPOTIFY_CALLBACK_URL,
            "response_type": "code",
            "state": state,
        }
    )

    return AUTH_URL + "?" + params


class RetryError(ConnectionError):
    pass


class SpotifyAuth(NamedTuple):
    user_id: str
    access_token: str
    refresh_token: str
    token_expires_at: int


blueprint = Blueprint("spotify")

cron_task = None


def start_cron(http_session):
    global cron_task
    cron_task = asyncio.get_event_loop().create_task(cron(http_session))


async def cron(http_session):
    logging.info("Starting spotify cron")
    try:
        while True:
            futures = []
            rows = await db.singleton.spotify_get()

            for row in rows:
                last_success_fetch = row["last_success_fetch"]
                fetch_fails_since_last = row["fetch_fails_since_last"]
                auth = SpotifyAuth(
                    row["user_id"],
                    row["access_token"],
                    row["refresh_token"],
                    row["token_expires_at"],
                )
                async with http_session() as session:
                    try:
                        auth, data = await get_latest_listens(
                            session, auth, after=row["last_success_fetch"], n=1
                        )
                    except:
                        logging.exception(
                            f"got err getting latest listens for {auth.user_id}"
                        )
                        continue
                    try:
                        if data:
                            data = data[0]
                            logging.debug(f"got data from spotify: {data}")
                            futures.append(
                                rendering.render_async(
                                    user_name=row["user_name"],
                                    user_id=auth.user_id,
                                    **data,
                                )
                            )
                            futures.append(
                                db.singleton.spotify_update(
                                    played_at=data["played_at"], **auth._asdict()
                                )
                            )
                    except:
                        logging.exception("Error during rendering")
            await asyncio.gather(*futures)
            if not futures:
                await asyncio.sleep(settings.SPOTIFY_CRON_INTERVAL_SECONDS)
    except:
        logging.exception("cron errored")
    logging.info("exiting spotify cron")


def stop_cron():
    cron_task.cancel()


def build_topic(topic, hits):
    return {
        "name": topic["name"],
        "id": topic["id"],
        "hits": hits,
    }


@blueprint.route("/", methods=["GET"])
async def index(request):
    uuid = request.cookies.get(settings.SPOTIFY_COOKIE_NAME)
    if uuid:
        return response.html(
            SPOTIFY_INDEX_TEMPLATE.substitute(
                statusburo_created_snippet=(
                    '<a href="https://status.buro.earth/#spotify-form">\n'
                    f'<img src="https://status.buro.earth/images/{uuid}.gif"/>\n'
                    "</a>"
                ),
                showform="none",
                showuserimage="block",
                userimage=f"/images/{uuid}.gif",
                gif_wall=await get_latest_gif_wall(30),
            )
        )
    else:
        return response.html(
            SPOTIFY_INDEX_TEMPLATE.substitute(
                statusburo_created_snippet="",
                showform="block",
                showuserimage="none",
                userimage="",
                gif_wall=await get_latest_gif_wall(30),
            )
        )


@blueprint.route("/spotify/signout", methods=["GET"])
async def index(request):
    user_id = request.cookies.get(settings.SPOTIFY_COOKIE_NAME)
    await db.singleton.spotify_delete(user_id)
    resp = response.redirect("https://www.spotify.com/us/account/apps/")
    del resp.cookies[settings.SPOTIFY_COOKIE_NAME]
    return resp

@blueprint.route("/spotify/signup", methods=["POST"])
async def index(request):
    uuid = utils.create_uuid()
    username = request.form.get("username")
    public = request.form.get("public") == "public"

    return response.redirect(
        get_spotify_auth_link(
            json.dumps(
                {"uuid": uuid, "username": username, "public": public},
                separators=(",", ":"),
            )
        )
    )


@blueprint.route("/spotify/create", methods=["GET"])
async def index(request):
    code = request.args["code"]
    state = request.args.get("state")
    if not state:
        return response.html("400", 400)

    state = json.loads(state)

    uuid = state["uuid"]
    user_name = state["username"]
    public = state["public"]

    headers = {"Accept": "application/json"}
    data = dict(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        redirect_uri=settings.SPOTIFY_CALLBACK_URL,
        grant_type="authorization_code",
        code=code,
    )

    async with request.app.http_session() as session:
        async with session.post(TOKEN_URL, headers=headers, data=data) as http_response:
            response_data = await http_response.json()
            status = http_response.status

            if status >= 400:
                cause = response_data.get("error")
                cause_description = response_data.get("error_description")
                if cause_description.lower() == "authorization code expired":
                    raise utils.Redirect(
                        "/", f"cause:{cause}, description:{cause_description}"
                    )
                else:
                    http_response.raise_for_status()

    auth = SpotifyAuth(
        user_id=uuid,
        access_token=response_data["access_token"],
        refresh_token=response_data["refresh_token"],
        token_expires_at=int(time.time()) + int(response_data["expires_in"]),
    )
    await db.singleton.spotify_create(
        user_name=user_name, public=public, **auth._asdict()
    )
    sleep_n = 30
    for i in range(sleep_n):
        if os.path.exists("/images/{uuid}.gif"):
            break
        asyncio.sleep(4/sleep_n)
    asyncio.sleep(1)
    resp = response.redirect("/")
    resp.cookies[settings.SPOTIFY_COOKIE_NAME] = uuid
    return resp


async def refresh_token(session, auth):
    data = dict(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        grant_type="refresh_token",
        refresh_token=auth.refresh_token,
    )
    async with session.post(TOKEN_URL, data=data) as response:
        response.raise_for_status()

        response_data = await response.json()

        status = response.status

    if status >= 400:
        cause = response_data.get("error")
        cause_description = response_data.get("error_description")
        if status == 400 and cause == "invalid_grant":
            await db.singleton.spotify_delete(auth.user_id)

    return SpotifyAuth(
        user_id=auth.user_id,
        access_token=response_data["access_token"],
        refresh_token=response_data.get("refresh_token", auth.refresh_token),
        token_expires_at=int(time.time()) + int(response_data["expires_in"]),
    )


async def get_latest_listens(session, auth, tries=3, after=0, n=1):
    if auth.token_expires_at - time.time() <= 60:
        auth = await refresh_token(session, auth)

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {auth.access_token}",
    }

    async with session.get(
        API_URL + f"/me/player/recently-played?limit={n}&after={after}", headers=headers
    ) as response:
        if response.status == 429:
            tries -= 1
            if tries >= 0:
                logging.warning(
                    f"got rate limited, sleeping {response.headers['Retry-After']} seconds"
                )
                await asyncio.sleep(int(response.headers["Retry-After"]))
                return await get_latest_listens(session, auth, tries, n)

        response.raise_for_status()
        data = await response.json()
        items = []
        for d in data["items"]:
            items.append(
                {
                    "track_name": d["track"]["name"],
                    "album_name": d["track"]["album"]["name"],
                    "release_date": d["track"]["album"]["release_date"],
                    "played_at": utils.parse_date(d["played_at"]),
                    "url": d["track"].get("external_urls", {}).get("spotify"),
                    "artist_name": d["track"]["artists"][0]["name"],
                }
            )

        return auth, items
