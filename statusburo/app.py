import trustpilot_json_logging

logging = trustpilot_json_logging.setup_logging("INFO")


import time
import io
import asyncio
from collections import defaultdict, deque
import string
from urllib.parse import urlparse
from statusburo import settings, spotify, db, utils
import aiohttp
from sanic import Sanic
from sanic import response
from sanic.exceptions import (
    _sanic_exceptions,
    SanicException,
    InvalidUsage,
    ServerError,
    RequestTimeout,
)


app = Sanic("statusburo")


@app.listener("before_server_start")
async def setup_db(app, loop):
    app.db = db.SqlLite()
    await app.db.setup(settings.DB_FILE)
    app.http_session = aiohttp.ClientSession
    spotify.start_cron(app.http_session)


@app.listener("before_server_stop")
async def notify_server_stopping(app, loop):
    await app.db.teardown()
    spotify.stop_cron()


app.blueprint(spotify.blueprint)


@app.exception(utils.Redirect)
def follow_redirects(request, exception):
    target_path = exception.target_path
    logging.warning({"message": "Got redirect", "exception": exception})
    return response.redirect(target_path)


@app.exception(InvalidUsage)
def ignore_400s(request, exception):
    return response.text(str(exception), status=400)


@app.exception(asyncio.TimeoutError)
def ignore_504(request, exception):
    logging.exception("Gateway timeout")
    return response.text("Gateway timeout", status=504)


@app.exception(RequestTimeout)
def ignore_408s(request, exception):
    """
    from https://sanic.readthedocs.io/en/latest/sanic/api_reference.html?highlight=RequestTimeout#sanic.exceptions.RequestTimeout
    The Web server (running the Web site) thinks that there has
    been too long an interval of time between 1) the establishment
    of an IP connection (socket) between the client and
    the server and 2) the receipt of any data on that socket,
    so the server has dropped the connection.
    The socket connection has actually been lost - the Web server
    has ‘timed out’ on that particular socket connection.
    """
    return response.text("HTTP connection terminated", 408)


@app.exception(SanicException)
@app.exception(ServerError)
@app.exception(Exception)
def ignore_all_unhandled_sanic_exceptions(request, exception):
    status_code = getattr(exception, "status_code", None)
    exception_name = "HttpError"

    if status_code is None or status_code >= 500:
        logging.exception(
            {
                "message": "Internal server error",
                "exception": exception,
                "status": status_code,
                "fullPath": request.path,
            }
        )
        return response.text("Internal server error", status=status_code or 500)
    else:
        exception_cls = _sanic_exceptions.get(status_code)
        exception_name = exception_cls.__name__

        logging.debug(
            {
                "message": "HttpError handler",
                "name": exception_name,
                "status": status_code,
                "fullPath": request.path,
            }
        )

        return response.text(exception_name, status=status_code)


def run():
    app.run(host="0.0.0.0", port=9002, access_log=False)


if __name__ == "__main__":
    run()
