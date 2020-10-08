import os

from PIL import Image, ImageFont, ImageDraw
from pygifsicle import gifsicle
import datetime
import timeago
import tempfile
import logging
import asyncio
from shutil import copyfile


CACHE = {}

background_color = (26, 26, 26)
artist_album_color = (0, 219, 212)
track_color = (3, 252, 119)
time_color = (255, 110, 217)
right_margin = 5
left_margin = 5
top_bottom_margin = 5


def get_background_image(width, height):
    key = f"{width}_{height}"
    background_image = CACHE.get(key)
    if not background_image:
        background_image = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(background_image)
        draw.ellipse(
            ((0, 0), (left_margin * 3, left_margin * 3)), fill=background_color
        )
        draw.ellipse(
            ((0, height - left_margin * 3), (left_margin * 3, height)),
            fill=background_color,
        )
        draw.ellipse(
            ((width - left_margin * 3, 0), (width, left_margin * 3)),
            fill=background_color,
        )
        draw.ellipse(
            ((width - left_margin * 3, height - left_margin * 3), (width, height)),
            fill=background_color,
        )
        draw.rectangle(
            [(0, left_margin), (width, height - left_margin)], fill=background_color
        )
        draw.rectangle(
            [(left_margin, 0), (width - left_margin, height)], fill=background_color
        )
        CACHE[key] = background_image
    return background_image.copy()


def render(
    user_id,
    user_name,
    artist_name,
    track_name,
    album_name,
    release_date,
    played_at,
    *args,
    **kwargs,
):
    images = []
    width = 250

    x_step = 7
    font_size = 15
    height = font_size * 4 + (top_bottom_margin * 2)

    user_name = user_name or ""

    time_string = timeago.format(
        played_at.replace(tzinfo=None), datetime.datetime.utcnow().replace(tzinfo=None)
    )
    if user_name:
        time_string = f"{time_string} {user_name} listened to"

    album_name += f" ({release_date[:4]})"

    current_dir = os.path.dirname(__file__)

    font = ImageFont.truetype(f"{current_dir}/COMIC.TTF", font_size)

    time_string_width = font.getsize(time_string)[0]
    artist_name_width = font.getsize(artist_name)[0]
    track_name_width = font.getsize(track_name)[0]
    album_name_width = font.getsize(album_name)[0]
    max_width = max(
        time_string_width, artist_name_width, track_name_width, album_name_width
    )
    x_margin = (
        max(
            font.getsize("when:")[0],
            font.getsize("artist:")[0],
            font.getsize("album:")[0],
            font.getsize("track:")[0],
        )
        + 10
    )

    x_offset = x_margin
    index = 0

    def frame(
        output_dir,
        x_offset,
        scroll_time=False,
        scroll_artist=False,
        scroll_album=False,
        scroll_track=False,
    ):
        nonlocal index
        im = get_background_image(width, height)

        draw = ImageDraw.Draw(im)

        y = 0
        y_growth = font_size

        y += y_growth
        if scroll_artist:
            draw.text((x_offset, y), artist_name, font=font, fill=artist_album_color)
            draw.text(
                (x_offset + x_margin + max_width, y),
                artist_name,
                font=font,
                fill=artist_album_color,
            )
        else:
            draw.text((x_margin, y), artist_name, font=font, fill=artist_album_color)
        y += y_growth

        if scroll_album:
            draw.text((x_offset, y), album_name, font=font, fill=artist_album_color)
            draw.text(
                (x_offset + x_margin + max_width, y),
                album_name,
                font=font,
                fill=artist_album_color,
            )
        else:
            draw.text((x_margin, y), album_name, font=font, fill=artist_album_color)
        y += y_growth

        if scroll_track:
            draw.text((x_offset, y), track_name, font=font, fill=track_color)
            draw.text(
                (x_offset + x_margin + max_width, y),
                track_name,
                font=font,
                fill=track_color,
            )
        else:
            draw.text((x_margin, y), track_name, font=font, fill=track_color)

        draw.rectangle(
            [(0, left_margin), (x_margin, height - left_margin)], fill=background_color
        )
        draw.rectangle(
            [(width - right_margin, left_margin), (width, height - left_margin)],
            fill=background_color,
        )

        y = 0
        if scroll_time:
            draw.text((x_offset - x_margin, y), time_string, font=font, fill=time_color)
            draw.text(
                (x_offset + max_width + left_margin, y),
                time_string,
                font=font,
                fill=time_color,
            )
        else:
            draw.text((left_margin, y), time_string, font=font, fill=time_color)

        y += y_growth

        draw.text((left_margin, y), "artist:", font=font, fill=artist_album_color)
        y += y_growth

        draw.text((left_margin, y), "album:", font=font, fill=artist_album_color)
        y += y_growth

        draw.text((left_margin, y), "track:", font=font, fill=track_color)
        draw.rectangle(
            [(0, left_margin), (left_margin, height - left_margin)],
            fill=background_color,
        )

        filename = f"{output_dir}/{index}.gif"
        im.save(filename, optimize=True)
        index += 1
        return filename

    with tempfile.TemporaryDirectory(dir=current_dir) as tmpdirname:
        images.append(frame(tmpdirname, x_offset))

        excess_width = (max_width + x_margin) - (width - right_margin)
        if excess_width > 0:
            scroll_time = (time_string_width) > (width - right_margin)
            scroll_artist = (artist_name_width + x_margin) > (width - right_margin)
            scroll_track = (track_name_width + x_margin) > (width - right_margin)
            scroll_album = (album_name_width + x_margin) > (width - right_margin)
            for i in range(10):
                images.append(frame(tmpdirname, x_offset))
            for i in range(0, max_width + x_margin - x_step, x_step):
                x_offset -= x_step
                images.append(
                    frame(
                        tmpdirname,
                        x_offset,
                        scroll_time,
                        scroll_artist,
                        scroll_album,
                        scroll_track,
                    )
                )
        output_filename = f"{tmpdirname}/final.gif"
        gifsicle(
            images,
            output_filename,
            optimize=False,
            colors=7,
            options=["--delay", "1", "--transparent", "#000000", "--loopcount"],
        )
        copyfile(output_filename, f"./images/{user_id}.gif")


async def render_async(*args, **kwargs):
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, lambda: render(*args, **kwargs))
    except:
        logging.exception("err")


if __name__ == "__main__":
    render(
        "2323423",
        "sloev",
        "lolband",
        "really long and boring track name",
        "really long",
        "2020-01-01",
        datetime.datetime.now(),
    )
