# Acoustats
# Copyright (C) 2022 H. Kamran
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Acoustats Analyzer
Contributors:
    :: H. Kamran [@hkamran80] (author)
"""

import dateutil.relativedelta
import aiohttp_client_cache
import asyncspotify
import collections
import dataclasses
import termcolor
import datetime
import asyncio
import aiohttp
import dotenv
import typing
import enum
import json
import time
import math
import os

dotenv.load_dotenv()

USERNAME = os.environ.get("USERNAME", None)
LAST_FM_API_KEY = os.environ.get("LAST_FM_API_KEY", None)
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", None)
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", None)
RAW_DUMP = os.environ.get("RAW_DUMP", False)
OUTPUT = os.environ.get("ANALYZER_OUTPUT", False)
HISTORY_OUTPUT = os.environ.get("HISTORY_OUTPUT", False)

BASE_URL = "https://ws.audioscrobbler.com/2.0/"
HEADERS = {"User-Agent": "Acoustats Analyzer/1.0.0 ( hkamran@unisontech.org )"}

WORK_QUEUE = asyncio.Queue()
WORK_QUEUE_OUTPUT = []
ERROR = None
SPOTIFY_ACCESS_TOKEN = None
BasicTrackInfo = collections.namedtuple("BasicTrackInfo", "name artist album mbid")
VeryBasicTrackInfo = collections.namedtuple("VeryBasicTrackInfo", "name artist")

# Normal cache expires after a month
ASYNC_CACHE = aiohttp_client_cache.SQLiteBackend(
    cache_name="analyzer_tracks_cache",
    expire_after=2628000,
    allowed_methods=("GET", "POST"),
    allowed_codes=(200,),
    ignored_params=["api_key"],
)

# User cache expires after a week
ASYNC_USER_CACHE = aiohttp_client_cache.SQLiteBackend(
    cache_name=f"analyzer_lastfm_user_{USERNAME}",
    expire_after=86400,
    allowed_methods=("GET", "POST"),
    allowed_codes=(200,),
    ignored_params=["api_key"],
)


@dataclasses.dataclass
class Artist:
    name: str
    mbid: str


@dataclasses.dataclass
class Album:
    name: str
    mbid: str


@dataclasses.dataclass
class Track:
    name: str
    mbid: typing.Union[str, None]
    artist: Artist
    album: typing.Union[Album, None]


@dataclasses.dataclass
class RecentTrack(Track):
    now_playing: bool
    epoch_started: int


@dataclasses.dataclass
class RecentTrackWithDuration(RecentTrack):
    duration: int


@dataclasses.dataclass
class TrackInfo(Track):
    duration: int
    playcount: int


@dataclasses.dataclass
class CachedHTTPResponse:
    response: dict
    from_cache: bool


class Timeframe(enum.Enum):
    TODAY = "today"
    THIS_WEEK = "this week"
    THIS_MONTH = "this month"
    THIS_YEAR = "this year"
    YESTERDAY = "yesterday"
    LAST_WEEK = "last week"
    LAST_MONTH = "last month"
    LAST_YEAR = "last year"

    @classmethod
    def list_names(cls):
        return list(map(lambda c: c.name, cls))

    @classmethod
    def list_values(cls):
        return list(map(lambda c: c.value, cls))


class DataclassEncoder(json.JSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return obj.__dict__

        return json.JSONEncoder.default(self, obj)


def strip_quotes(string: str) -> str:
    return string.replace('"', "")


def remove_null(null_filled: list) -> list:
    return [item for item in null_filled if item]


def last_sunday(d: datetime.date) -> datetime.date:
    # 0 - Sunday
    target_day = 0
    delta_day = target_day - d.isoweekday()

    if delta_day >= 0:
        delta_day -= 7

    return d + datetime.timedelta(days=delta_day)


def value_counter(values: list, output: bool = False) -> list:
    value_counts: dict = {}
    value_counter = collections.Counter(values)

    for value, occurrences in value_counter.most_common():
        if occurrences in value_counts:
            value_counts[occurrences].append(value)
        else:
            value_counts[occurrences] = [value]

    if output:
        print(value_counts)

    if value_counts:
        return value_counts[max(value_counts)]
    else:
        return []


def get_duration(track: RecentTrack, unique_track_info: typing.List[TrackInfo]) -> int:
    durations = [
        unique_track.duration
        for unique_track in unique_track_info
        if unique_track.name == track.name and unique_track.artist == track.artist
    ]

    if len(durations) != 0:
        return durations[0]

    return 0


def join_strings(strings: typing.List[str]) -> str:
    if len(strings) > 2:
        return ", ".join(strings[:-1]) + ", and " + str(strings[-1])
    elif len(strings) == 2:
        return " and ".join(strings)
    elif len(strings) == 1:
        return strings[0]


def basic_pluralize(word: str, count: int) -> str:
    if count != 1:
        return word + "s"

    return word


async def async_http_get(
    url: str, headers: dict = {}, params: dict = {}
) -> typing.Union[CachedHTTPResponse, None]:
    global ASYNC_CACHEs

    async with aiohttp_client_cache.CachedSession(cache=ASYNC_CACHE) as session:
        try:
            async with session.get(url, headers=headers, params=params) as response:
                if response.ok and response.text != "":
                    if not response.is_expired:
                        return CachedHTTPResponse(
                            await response.json(), response.from_cache
                        )
                    else:
                        print(f"Expired response ({url})")
                        await session.delete_expired_responses()
                        return await async_http_get(url, headers, params)
                else:
                    return None
        except Exception as e:
            print(f"URL: {url}")
            print(f"Headers: {headers}")
            print(f"Parameters: {params}")
            print(f"Error: {e}")

            return None


async def lastfm_aget(payload: dict) -> typing.Union[aiohttp.ClientResponse, None]:
    global ASYNC_CACHE, ASYNC_USER_CACHE, BASE_URL, HEADERS, LAST_FM_API_KEY

    payload["api_key"] = LAST_FM_API_KEY
    payload["format"] = "json"

    async with aiohttp_client_cache.CachedSession(
        cache=ASYNC_USER_CACHE if "user" in payload else ASYNC_CACHE
    ) as session:
        try:
            async with session.get(
                BASE_URL, headers=HEADERS, params=payload
            ) as response:
                if response.ok and response.text != "":
                    if not response.from_cache:
                        time.sleep(0.5)

                    if not response.is_expired:
                        return await response.json()
                    else:
                        print(f"Expired response ({payload})")
                        await session.delete_expired_responses()
                        return await lastfm_aget(payload)
                else:
                    return None
        except Exception as e:
            print(f"Parameters: {payload}")
            print(f"Error: {e}")
            return None


async def clear_work_queue() -> None:
    global WORK_QUEUE

    for _ in range(WORK_QUEUE.qsize()):
        WORK_QUEUE.get_nowait()
        WORK_QUEUE.task_done()


async def get_recent_tracks_page(
    page: int, output: bool = False
) -> typing.Union[list, None]:
    global USERNAME, ERROR

    if output:
        print(f"[GRTP] Retrieving page {page}...")

    recent_tracks = await lastfm_aget(
        {"method": "user.getRecentTracks", "user": USERNAME, "page": page}
    )

    if recent_tracks:
        if "error" in recent_tracks and recent_tracks["error"] == 29:
            await clear_work_queue()
            ERROR = "Rate limit exceeded"
            return None

    return recent_tracks


async def get_track_info(
    track: BasicTrackInfo, output: bool = False
) -> typing.Union[TrackInfo, None]:
    global ERROR

    if output:
        print(f"[GTIS] {track.name} ({track.artist})")

    track_info_request = await lastfm_aget(
        {
            "method": "track.getInfo",
            "track": track.name,
            "artist": track.artist,
        }
    )

    if track_info_request:
        if "error" in track_info_request and track_info_request["error"] == 29:
            await clear_work_queue()
            print("RLE")
            ERROR = "Rate limit exceeded"
            return None

        try:
            track_info = track_info_request["track"]
            return TrackInfo(
                track_info["name"],
                track.mbid,
                Artist(
                    track_info["artist"]["name"],
                    track_info["artist"].get("mbid", ""),
                ),
                Album(track_info["album"]["title"], "")
                if "album" in track_info
                else None,
                int(track_info["duration"]),
                int(track_info["playcount"]),
            )
        except Exception as e:
            print(e)
            print(type(track_info_request))
            print(track_info_request)

            return None
    else:
        return None


async def find_track(
    search_track: BasicTrackInfo, output: bool = False
) -> typing.Union[typing.Tuple[dict, BasicTrackInfo], None]:
    global SPOTIFY_ACCESS_TOKEN

    request = await async_http_get(
        "https://api.spotify.com/v1/search",
        headers={
            "Authorization": f"Bearer {SPOTIFY_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        params={"q": f"track:{search_track.name}", "type": "track", "limit": 5},
    )
    if request:
        tracks = request.response["tracks"]["items"]
        if len(tracks) != 0:
            for track in tracks:
                if output:
                    print(
                        f"{track['name']} ({', '.join([artist['name'] for artist in remove_null(track['artists'])])})"
                    )

                if track[
                    "name"
                ].lower() == search_track.name.lower() and search_track.artist.lower() in [
                    artist["name"].lower() for artist in remove_null(track["artists"])
                ]:
                    return (track, search_track)

            return None
        else:
            return None
    else:
        return None


async def get_musicbrainz_duration(
    search_track: BasicTrackInfo, output: bool = False
) -> typing.Union[typing.Tuple[int, BasicTrackInfo], None]:
    global HEADERS

    if output:
        print(search_track)

    response = await async_http_get(
        "https://musicbrainz.org/ws/2/recording",
        headers=HEADERS,
        params={
            "query": f"{search_track.name} artist:{search_track.artist}",
            "fmt": "json",
        },
    )

    if response:
        results = response.response["recordings"]
        if len(results) > 0:
            for result in results:
                if result["title"].replace(
                    "\u2019", "'"
                ).lower() != search_track.name.lower() or search_track.artist.lower() not in [
                    artist["name"].lower() for artist in result["artist-credit"]
                ]:
                    continue

                if search_track.mbid != "":
                    if output:
                        print("[GMBD] MBID provided, checking for matches...")

                    for release in result["releases"]:
                        for medium in release["media"]:
                            for track_list in medium["track"]:
                                if track_list["id"] == search_track.mbid:
                                    if output:
                                        print("[GMBD] MBID match")

                                    try:
                                        return (int(result["length"]), search_track)
                                    except Exception as error:
                                        print(f"[GMBD] {error}")
                                        return None

                    return None
                else:
                    if output:
                        print("[GMBD] No MBID provided")

                    try:
                        return (int(result["length"]), search_track)
                    except Exception as error:
                        print(f"[GMBD] Error: {error}")
                        return None

            return None

        return None

    return None


async def worker(
    name: str,
    executable: typing.Callable,
    output: bool = False,
):
    global WORK_QUEUE, WORK_QUEUE_OUTPUT

    if output:
        print(f"[WORKER::{name}] Started")

    while not WORK_QUEUE.empty():
        item = await WORK_QUEUE.get()

        if output:
            print(f"[WORKER::{name}] {WORK_QUEUE.qsize()} items left")

        WORK_QUEUE_OUTPUT.append(await executable(item, output))


async def start_workers(
    worker_prefix: str,
    executable: typing.Callable,
    clear_work_queue_output: bool = True,
    worker_count: int = 5,
    output: bool = False,
) -> None:
    global WORK_QUEUE_OUTPUT

    if clear_work_queue_output:
        WORK_QUEUE_OUTPUT.clear()

    await asyncio.gather(
        *[
            worker(f"{worker_prefix}.{worker_index}", executable, output)
            for worker_index in range(worker_count)
        ],
    )


async def get_unique_tracks(
    tracks: typing.List[RecentTrack],
) -> typing.Union[
    typing.Tuple[typing.List[typing.Set[BasicTrackInfo]], typing.List[TrackInfo]],
    None,
]:
    global WORK_QUEUE_OUTPUT, WORK_QUEUE, SPOTIFY_ACCESS_TOKEN, OUTPUT

    unique_tracks: typing.List[typing.Set[BasicTrackInfo]] = list(
        set(
            [
                BasicTrackInfo(
                    track.name,
                    track.artist.name,
                    track.album.name if track.album else None,
                    track.mbid,
                )
                for track in tracks
            ]
        )
    )

    termcolor.cprint("Retrieving unique track information...", attrs=["bold"])
    for track in unique_tracks:
        await WORK_QUEUE.put(track)

    await start_workers("GTI", get_track_info, output=OUTPUT)
    if ERROR:
        exit(ERROR)

    unique_track_info: typing.List[TrackInfo] = remove_null(WORK_QUEUE_OUTPUT)

    print()

    no_duration_tracks: typing.List[TrackInfo] = [
        track for track in unique_track_info if track.duration == 0
    ]
    print(f"Tracks with no duration: {len(no_duration_tracks)}")

    if len(no_duration_tracks) != 0:
        if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
            async with asyncspotify.Client(
                asyncspotify.ClientCredentialsFlow(
                    SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
                )
            ) as sp:
                SPOTIFY_ACCESS_TOKEN = sp.auth.header["Authorization"].split(" ")[1]

            termcolor.cprint(
                "Retrieving durations for no duration tracks (Spotify)...",
                attrs=["bold"],
            )
            for track in no_duration_tracks:
                album_name: typing.Union[str, None] = (
                    track.album.name if track.album else None
                )
                if not album_name:
                    og_track: typing.List[RecentTrack] = [
                        _track
                        for _track in tracks
                        if _track.name == track.name and _track.artist == track.artist
                    ]

                    if len(og_track) > 0 and og_track[0].album:
                        album_name: str = og_track[0].album.name

                await WORK_QUEUE.put(
                    BasicTrackInfo(
                        track.name, track.artist.name, album_name, track.mbid
                    )
                )

            await start_workers("SFTD", find_track, output=OUTPUT)
            if ERROR:
                exit(ERROR)

            pre_spotify_uti: typing.List[TrackInfo] = [
                track for track in unique_track_info if track.duration == 0
            ]

            for output_item in remove_null(WORK_QUEUE_OUTPUT):
                track, search_track = output_item

                unique_track: typing.List[
                    typing.Union[typing.List[TrackInfo], TrackInfo]
                ] = [
                    track
                    for track in unique_track_info
                    if track.name == search_track.name
                ]
                if len(unique_track) > 0:
                    unique_track: TrackInfo = unique_track[0]
                    unique_track_index: int = unique_track_info.index(unique_track)
                else:
                    termcolor.cprint("Unique track not found", "red")
                    continue

                unique_track_info[unique_track_index] = dataclasses.replace(
                    unique_track, duration=int(track["duration_ms"])
                )

            post_spotify_uti: typing.List[TrackInfo] = [
                track for track in unique_track_info if track.duration == 0
            ]

            print(
                f"Spotify durations found: {len(pre_spotify_uti) - len(post_spotify_uti)}"
            )

        termcolor.cprint(
            "Retrieving durations for no duration tracks (MusicBrainz)...",
            attrs=["bold"],
        )
        for item in [track for track in unique_track_info if track.duration == 0]:
            await WORK_QUEUE.put(
                BasicTrackInfo(
                    item.name,
                    item.artist.name,
                    item.album.name if item.album else None,
                    item.mbid,
                )
            )

        await start_workers("MBD", get_musicbrainz_duration, output=OUTPUT)
        if ERROR:
            exit(ERROR)

        for output in remove_null(WORK_QUEUE_OUTPUT):
            duration, search_track = output

            unique_track: typing.List[
                typing.Union[typing.List[TrackInfo], TrackInfo]
            ] = [
                track for track in unique_track_info if track.name == search_track.name
            ]
            if len(unique_track) > 0:
                unique_track: TrackInfo = unique_track[0]
                unique_track_index: int = unique_track_info.index(unique_track)
            else:
                termcolor.cprint("Unique track not found", "red")
                continue

            unique_track_info[unique_track_index] = dataclasses.replace(
                unique_track, duration=duration
            )

        post_duration_uti: typing.List[TrackInfo] = [
            track for track in unique_track_info if track.duration == 0
        ]

        if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
            print(
                f"MusicBrainz durations found: {len(post_spotify_uti) - len(remove_null(WORK_QUEUE_OUTPUT))}"
            )
            print(
                f"Total durations found: {len(pre_spotify_uti) - len(post_duration_uti)}"
            )
        else:
            print(f"MusicBrainz durations found: {len(remove_null(WORK_QUEUE_OUTPUT))}")

        print(f"Tracks without durations: {len(post_duration_uti)}")

    if unique_tracks and unique_track_info:
        return (unique_track, unique_track_info)
    else:
        return None


async def get_recent_tracks() -> typing.Union[
    typing.Tuple[typing.List[RecentTrack], typing.List[TrackInfo]],
    None,
]:
    global WORK_QUEUE_OUTPUT, WORK_QUEUE, OUTPUT, HISTORY_OUTPUT, USERNAME

    # Get recent tracks
    termcolor.cprint("Retrieving recent tracks...", attrs=["bold"])

    first_recent_page: typing.Union[aiohttp.ClientResponse, None] = await lastfm_aget(
        {"method": "user.getRecentTracks", "user": USERNAME, "page": 1}
    )
    if first_recent_page:
        first_recent_page_json: dict = first_recent_page

        for page in range(
            2,
            int(first_recent_page_json["recenttracks"]["@attr"]["totalPages"]) + 1,
        ):
            await WORK_QUEUE.put(page)

        WORK_QUEUE_OUTPUT.append(first_recent_page_json)
    else:
        print(first_recent_page.status_code)
        print(first_recent_page.text)

        exit(termcolor.colored("Unable to retrieve recent tracks", "red"))

    await start_workers(
        "GRT", get_recent_tracks_page, clear_work_queue_output=False, output=OUTPUT
    )
    if ERROR:
        exit(ERROR)

    paged_tracks: typing.List[dict] = [
        page["recenttracks"]["track"] for page in remove_null(WORK_QUEUE_OUTPUT)
    ]

    all_recent: typing.List[dict] = [
        item for sublist in paged_tracks for item in sublist
    ]

    for track in all_recent:
        try:
            track["name"]
        except TypeError:
            print(track)
            print(all_recent.index(track))

    tracks: typing.List[RecentTrack] = [
        RecentTrack(
            track["name"],
            track["mbid"],
            Artist(track["artist"]["#text"], track["artist"]["mbid"]),
            Album(track["album"]["#text"], track["album"]["mbid"]),
            json.loads(track["@attr"]["nowplaying"])
            if "@attr" in track and "nowplaying" in track["@attr"]
            else False,
            0
            if "@attr" in track and "nowplaying" in track["@attr"]
            else int(track["date"]["uts"]),
        )
        for track in all_recent
    ]

    if HISTORY_OUTPUT:
        with open(f"tracks_{USERNAME}.csv", "w") as tracks_file:
            tracks_file.write(
                "\n".join(
                    [
                        "trackName,artistName,albumName,nowPlaying,epochStarted",
                        *[
                            f'"{strip_quotes(track.name)}","{strip_quotes(track.artist.name)}","{strip_quotes(track.album.name)}",{json.dumps(track.now_playing)},{track.epoch_started}'
                            for track in tracks
                        ],
                    ]
                )
            )

    # Find unique tracks
    unique_tracks_raw = await get_unique_tracks(tracks)
    if unique_tracks_raw:
        unique_tracks, unique_track_info = unique_tracks_raw

    if tracks and unique_tracks:
        return (tracks, unique_track_info)
    else:
        return None


async def analyze_tracks(
    recent_tracks: typing.List[RecentTrackWithDuration],
) -> typing.Tuple[
    typing.List[VeryBasicTrackInfo], typing.List[Artist], typing.List[Album], int
]:
    tracks: typing.List[VeryBasicTrackInfo] = [
        VeryBasicTrackInfo(track.name, track.artist.name if track.artist else "N/A")
        for track in recent_tracks
    ]
    artists: typing.List[Artist] = [track.artist for track in recent_tracks]
    albums: typing.List[Album] = [track.album for track in recent_tracks if track.album]

    top_tracks_raw: typing.List[str] = value_counter([track.name for track in tracks])
    top_tracks: typing.List[VeryBasicTrackInfo] = []

    for top_track in top_tracks_raw:
        for track in tracks:
            if track.name == top_track:
                top_tracks.append(track)
                break

    top_artists_raw: typing.List[str] = value_counter(
        [artist.name for artist in artists]
    )
    top_artists: typing.List[Artist] = []

    for top_artist in top_artists_raw:
        for artist in artists:
            if artist.name == top_artist:
                top_artists.append(artist)
                break

    top_albums_raw: typing.List[str] = value_counter([album.name for album in albums])
    top_albums: typing.List[Album] = []

    for top_album in top_albums_raw:
        for album in albums:
            if album.name == top_album:
                top_albums.append(album)
                break

    total_duration = sum([track.duration for track in recent_tracks])

    if not top_tracks:
        top_tracks = []

    if not top_artists:
        top_artists = []

    if not top_albums:
        top_albums = []

    return (top_tracks, top_artists, top_albums, total_duration)


async def generate_analysis_messages(
    analysis: typing.Tuple[
        typing.List[VeryBasicTrackInfo], typing.List[Artist], typing.List[Album], int
    ]
) -> dict:
    top_tracks, top_artists, top_albums, total_duration = analysis

    raw_minutes = total_duration / 1000 / 60
    hours = math.floor(raw_minutes / 60)
    minutes = math.floor(raw_minutes - (hours * 60))
    seconds = round((total_duration / 1000) - (math.floor(raw_minutes) * 60))

    duration_message = "You listened for "
    if hours:
        duration_message += f"{hours} {'hours' if hours != 1 else 'hour'}, "

    if minutes:
        duration_message += f"{minutes} {'minutes' if minutes != 1 else 'minute'}, "

    if "hours" in duration_message or "minutes" in duration_message:
        duration_message += "and "

    duration_message += f"{seconds} {'seconds' if seconds != 1 else 'second'}"

    if not RAW_DUMP:
        messages = {
            "toptrack": f"Your top track{'s were' if len(top_tracks) != 1 else ' was'} "
            + join_strings(
                [f"{top_track.name} ({top_track.artist})" for top_track in top_tracks]
            ),
            "topartist": f"Your top artist{'s were' if len(top_artists) != 1 else ' was'} "
            + join_strings([top_artist.name for top_artist in top_artists]),
            "topalbum": f"Your top album{'s were' if len(top_albums) != 1 else ' was'} "
            + join_strings([top_album.name for top_album in top_albums]),
            "duration": duration_message,
        }
    else:
        messages = {
            "toptrack": join_strings(
                [f"{top_track.name} ({top_track.artist})" for top_track in top_tracks]
            ),
            "topartist": join_strings([top_artist.name for top_artist in top_artists]),
            "topalbum": join_strings([top_album.name for top_album in top_albums]),
            "duration": duration_message.replace("You listened for ", ""),
            "duration_datetime": f"T{hours}H{minutes}M{seconds}S",
        }

    return messages


async def main(
    timeframe: Timeframe = Timeframe.LAST_WEEK,
) -> typing.Union[typing.List[RecentTrackWithDuration], dict]:
    tracks = await get_recent_tracks()
    if not tracks:
        exit(termcolor.colored("Recent tracks not available", "red"))

    recent_tracks, unique_track_info = tracks

    timeframe_tracks: typing.List[RecentTrack] = []
    if timeframe == Timeframe.TODAY:
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        today_timestamp = int(
            datetime.datetime(today.year, today.month, today.day, 0, 0, 0).timestamp()
        )
        tomorrow_timestamp = int(
            datetime.datetime(
                tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0
            ).timestamp()
        )

        timeframe_tracks = [
            track
            for track in recent_tracks
            if tomorrow_timestamp > track.epoch_started > today_timestamp
        ]
    elif timeframe == Timeframe.THIS_WEEK:
        sunday = last_sunday(datetime.date.today())

        timeframe_tracks = [
            track
            for track in recent_tracks
            if 0
            <= (datetime.date.fromtimestamp(track.epoch_started) - sunday).days
            <= 7
        ]
    elif timeframe == Timeframe.THIS_MONTH:
        this_month = datetime.date.today()
        next_month = this_month + dateutil.relativedelta.relativedelta(months=1)
        this_month_timestamp = int(
            datetime.datetime(this_month.year, this_month.month, 1, 0, 0, 0).timestamp()
        )
        next_month_timestamp = int(
            datetime.datetime(next_month.year, next_month.month, 1, 0, 0, 0).timestamp()
        )

        timeframe_tracks = [
            track
            for track in recent_tracks
            if next_month_timestamp > track.epoch_started > this_month_timestamp
        ]
    elif timeframe == Timeframe.THIS_YEAR:
        this_year = datetime.date.today()
        next_year = this_year + dateutil.relativedelta.relativedelta(years=1)
        this_year_timestamp = int(
            datetime.datetime(this_year.year, 1, 1, 0, 0, 0).timestamp()
        )
        next_year_timestamp = int(
            datetime.datetime(next_year.year, 1, 1, 0, 0, 0).timestamp()
        )

        timeframe_tracks = [
            track
            for track in recent_tracks
            if next_year_timestamp > track.epoch_started > this_year_timestamp
        ]

    elif timeframe == Timeframe.YESTERDAY:
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        today_timestamp = int(
            datetime.datetime(today.year, today.month, today.day, 0, 0, 0).timestamp()
        )
        yesterday_timestamp = int(
            datetime.datetime(
                yesterday.year, yesterday.month, yesterday.day, 0, 0, 0
            ).timestamp()
        )

        timeframe_tracks = [
            track
            for track in recent_tracks
            if today_timestamp > track.epoch_started > yesterday_timestamp
        ]
    elif timeframe == Timeframe.LAST_WEEK:
        sunday = last_sunday(
            datetime.date.today() - dateutil.relativedelta.relativedelta(weeks=1)
        )

        timeframe_tracks = [
            track
            for track in recent_tracks
            if 7
            <= (datetime.date.fromtimestamp(track.epoch_started) - sunday).days
            <= 14
        ]
    elif timeframe == Timeframe.LAST_MONTH:
        this_month = datetime.date.today()
        last_month = this_month - dateutil.relativedelta.relativedelta(months=1)
        this_month_timestamp = int(
            datetime.datetime(this_month.year, this_month.month, 1, 0, 0, 0).timestamp()
        )
        last_month_timestamp = int(
            datetime.datetime(last_month.year, last_month.month, 1, 0, 0, 0).timestamp()
        )

        timeframe_tracks = [
            track
            for track in recent_tracks
            if this_month_timestamp > track.epoch_started > last_month_timestamp
        ]
    elif timeframe == Timeframe.LAST_YEAR:
        this_year = datetime.date.today()
        last_year = this_year - dateutil.relativedelta.relativedelta(years=1)
        this_year_timestamp = int(
            datetime.datetime(this_year.year, 1, 1, 0, 0, 0).timestamp()
        )
        last_year_timestamp = int(
            datetime.datetime(last_year.year, 1, 1, 0, 0, 0).timestamp()
        )

        timeframe_tracks = [
            track
            for track in recent_tracks
            if this_year_timestamp > track.epoch_started > last_year_timestamp
        ]

    analyzed_tracks = await analyze_tracks(
        [
            RecentTrackWithDuration(
                track.name,
                track.mbid,
                track.artist,
                track.album,
                track.now_playing,
                track.epoch_started,
                get_duration(track, unique_track_info),
            )
            for track in timeframe_tracks
        ]
    )

    generated_messages = await generate_analysis_messages(analyzed_tracks)
    generated_messages["tracks"] = (
        f"You listened to {'{:,}'.format(len(timeframe_tracks))} {basic_pluralize('track', len(timeframe_tracks))}"
        if not RAW_DUMP
        else len(timeframe_tracks)
    )
    generated_messages["timeframe"] = timeframe.value.lower()

    return [timeframe_tracks, generated_messages]


if __name__ == "__main__":
    if not USERNAME or not LAST_FM_API_KEY:
        exit(
            termcolor.colored(
                f"You must set the {termcolor.colored('USERNAME', attrs=['bold'])} and {termcolor.colored('LAST_FM_API_KEY', attrs=['bold'])} environment variables!",
                "red",
            )
        )

    timeframe: Timeframe = list(Timeframe)[
        Timeframe.list_names().index(os.environ.get("TIMEFRAME", "THIS_WEEK"))
    ]
    tracks, generated_messages = asyncio.run(main(timeframe))

    with open(f"user_output_{USERNAME}.json", "w") as user_output:
        user_output.write(json.dumps(generated_messages))

    if OUTPUT:
        print()
        print(f"{timeframe.value.capitalize()}")
        for message in generated_messages:
            print(generated_messages[message])
