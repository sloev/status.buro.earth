from collections import defaultdict
from asyncio import Queue, Lock
import asyncio
from contextlib import asynccontextmanager
import time
import os
import aiosqlite
from datetime import date, datetime, timedelta
import logging
from collections import deque

from statusburo import settings


def get_current_date_string():
    today = date.today()
    return datetime(year=today.year, month=today.month, day=today.day).isoformat()


def get_current_datetime_string():
    return datetime.now().isoformat()


START_TIMESTAMP = get_current_date_string()

singleton = None


class SqlLite:
    def __init__(self):
        self.TOPICS_REGISTRY = defaultdict(dict)
        self.PUB_SUB_LOCK = Lock()
        self.db = None

    async def setup(self, sqlite_filename):
        self.db = await aiosqlite.connect(sqlite_filename)
        try:
            await self.db.execute(
                """
            CREATE TABLE IF NOT EXISTS spotify_oauth (
                user_id TEXT NOT NULL PRIMARY KEY,
                user_name TEXT,
                public INTEGER default 0,
                last_success_fetch INTEGER default 0,
                fetch_fails_since_last INTEGER default 0,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                token_expires_at INTEGER NOT NULL
            );
            """
            )
            await self.db.commit()
        except:
            logging.exception("Error creating db")
            raise
        global singleton
        singleton = self

    async def teardown(self):
        await self.db.close()
    
    async def spotify_delete(self,user_id):
        await self.db.execute(
                """
            delete from spotify_oauth
            where user_id = ?;
            """,
            [user_id]
            )
        await self.db.commit()

    async def spotify_get_latest_public(self, n=10):
        async with self.db.execute(
            """
            SELECT 
                user_id
            FROM spotify_oauth 
            where public = 1
            order by 
                last_success_fetch desc
            limit ?;
        """,
            [n],
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

    async def spotify_get(self, n=10):
        utc_before = int(
            (
                datetime.utcnow()
                - timedelta(minutes=settings.SPOTIFY_MINUTES_BETWEEN_REFRESH)
            ).timestamp()
            * 1000.0
        )
        async with self.db.execute(
            """
            SELECT 
                user_id,
                user_name,
                last_success_fetch, 
                fetch_fails_since_last, 
                access_token,
                refresh_token,
                token_expires_at
            FROM spotify_oauth 
            where 
                last_success_fetch < ?
            order by 
                last_success_fetch asc
            limit ?;
        """,
            [utc_before, n],
        ) as cursor:
            rows = await cursor.fetchall()
            keys = [
                "user_id",
                "user_name",
                "last_success_fetch",
                "fetch_fails_since_last",
                "access_token",
                "refresh_token",
                "token_expires_at",
            ]
            return [dict(zip(keys, values)) for values in rows]

    async def spotify_update(
        self,
        user_id,
        access_token,
        refresh_token,
        token_expires_at,
        played_at=None,
        error=False,
    ):
        played_at = played_at or datetime.utcnow()
        played_at_epoch_ms = int(played_at.timestamp() * 1000.0)
        await self.db.execute(
            """
            update spotify_oauth
            SET 
                last_success_fetch=?, 
                access_token=?,
                refresh_token=?,
                token_expires_at=?
            where user_id = ?
        """,
            [
                played_at_epoch_ms,
                access_token,
                refresh_token,
                token_expires_at,
                user_id,
            ],
        )
        await self.db.commit()

    async def spotify_create(
        self,
        user_id,
        public,
        access_token,
        refresh_token,
        token_expires_at,
        user_name=None,
    ):
        utc_now = int((datetime.utcnow() - timedelta(hours=24)).timestamp() * 1000.0)
        await self.db.execute(
            """
            insert into spotify_oauth(
                last_success_fetch,
                user_id, 
                user_name,
                public, 
                access_token,
                refresh_token,
                token_expires_at
            )
            values(?, ?, ?, ?, ?, ?, ?)
        """,
            [
                utc_now,
                user_id,
                user_name,
                int(public),
                access_token,
                refresh_token,
                token_expires_at,
            ],
        )
        await self.db.commit()

    # async def publish(self, topic, author, message):
    #     timestamp = get_current_datetime_string()
    #     await self.db.execute(
    #         f"INSERT INTO messages values(?,?,?,?);",
    #         [topic, timestamp, message, author],
    #     )
    #     await self.db.commit()

    # async def subscribe(self, topic):
    #     current_date = get_current_datetime_string()
    #     last_message = time.time()
    #     try:
    #         yield 0, None
    #         messages = deque()
    #         await self.db.execute(
    #             """
    #             INSERT INTO analytics_subscribers (topic, start)
    #                 VALUES(?, ?);
    #         """,
    #             [
    #                 topic,
    #                 current_date,
    #             ],
    #         )

    #         await self.db.commit()

    #         timestamp = START_TIMESTAMP
    #         async with self.db.execute(
    #             """
    #             SELECT author, message, timestamp
    #             FROM messages
    #             where topic = ?
    #             order by timestamp desc limit 10;
    #         """,
    #             [topic],
    #         ) as cursor:
    #             async for row in cursor:
    #                 messages.append(row[:2])
    #                 timestamp = row[2]
    #         got_message_last_time = True
    #         while True:
    #             async with self.db.execute(
    #                 """
    #                 select count(*)
    #                 from analytics_subscribers
    #                 where topic = ? and end is null;
    #             """,
    #                 [topic],
    #             ) as cursor:
    #                 row = await cursor.fetchone()
    #                 visitors = int(row[0])

    #             got_message = False
    #             async with self.db.execute(
    #                 """
    #                 SELECT author, message, timestamp
    #                 FROM messages
    #                 where topic = ?
    #                     and datetime(timestamp) > datetime(?)
    #                 order by timestamp asc;
    #             """,
    #                 [topic, timestamp],
    #             ) as cursor:
    #                 async for row in cursor:
    #                     messages.append(row[:2])
    #                     timestamp = row[2]
    #                     got_message = True
    #             while True:
    #                 try:
    #                     yield visitors, messages.pop()
    #                     last_message = time.time()
    #                 except IndexError:
    #                     break

    #             if got_message != got_message_last_time or time.time() >  last_message+10:
    #                 yield visitors, None
    #                 yield visitors, None
    #             got_message_last_time = got_message
    #             await asyncio.sleep(1)
    #     except:
    #         logging.exception("err")
    #     finally:
    #         await self.db.execute(
    #             """
    #             UPDATE analytics_subscribers
    #             SET end = ?
    #             where topic = ? and start = ?
    #         """,
    #             [get_current_datetime_string(), topic, current_date],
    #         )

    #         await self.db.commit()
