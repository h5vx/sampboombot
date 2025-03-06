import io
import logging
import os
import urllib
import urllib.parse
import typing as t
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import reduce

import requests
from bs4 import BeautifulSoup
from Levenshtein import distance
from yt_dlp import YoutubeDL

from config import settings

logger = logging.getLogger(__name__)


@dataclass()
class Track:
    artist: str
    title: str
    length: str
    download_url: str

    buf: io.BytesIO = None
    requester: str = ""

    def get_filename(self):
        normalized_url = urllib.parse.unquote(self.download_url)
        urlpath = urllib.parse.urlsplit(normalized_url).path
        return os.path.basename(urlpath)


def sorted_tracks(tracks: list[Track], song_name: str) -> list[Track]:
    sorter = lambda track: distance(
        f"{track.artist} {track.title}", song_name, processor=str.lower
    )
    return list(sorted(tracks, key=sorter))


class BaseSearcher:
    pass


class HitmoSearcher(BaseSearcher):
    BASE_URL = "https://rus.hitmotop.com"

    @classmethod
    def find_song(cls, song_name: str) -> list[Track]:
        song_name_a = "+".join(song_name.split())
        url = f"{cls.BASE_URL}/search?q={song_name_a}"

        try:
            r = requests.get(url, timeout=settings.searcher.request_timeout)
        except requests.exceptions.Timeout:
            return []

        bs = BeautifulSoup(r.text, features="html.parser")
        tracks = bs.find_all("li", {"class": "tracks__item"})

        track_list = []
        for i, track in enumerate(tracks):
            try:
                track_list.append(cls.parse_one_el(track))
            except Exception as e:
                logger.exception(
                    f"{cls.__name__}: For song '{song_name}': failed to parse {i} element"
                )

        return track_list

    @classmethod
    def parse_one_el(cls, el):
        return Track(
            title=el.find("div", {"class": "track__title"}).text.strip(),
            artist=el.find("div", {"class": "track__desc"}).text,
            length=el.find("div", {"class": "track__fulltime"}).text,
            download_url=el.find("a", {"class": "track__download-btn"})["href"],
        )


class HitmoLolSearcher(BaseSearcher):
    BASE_URL = "https://hitmo.lol"

    @classmethod
    def find_song(cls, song_name: str) -> list[Track]:
        url = f"{cls.BASE_URL}/pesnya/{song_name}"
        try:
            r = requests.get(url, timeout=settings.searcher.request_timeout)
        except requests.exceptions.Timeout:
            return []

        bs = BeautifulSoup(r.text, features="html.parser")
        tracks = bs.find_all("div", {"class": "track-item"})

        track_list = []
        for i, track in enumerate(tracks):
            try:
                track_list.append(cls.parse_one_el(track))
            except Exception as e:
                logger.exception(
                    f"{cls.__name__}: For song '{song_name}': failed to parse {i} element",
                )
        return track_list

    @classmethod
    def parse_one_el(cls, el):
        return Track(
            title=el.find("a", {"class": "muzmo-track__title"}).text.strip(),
            artist=el.find("span", {"class": "muzmo-track__artist"}).text,
            length=el.find("span", {"class": "short-track__time"}).text,
            download_url=cls.BASE_URL + el["data-file"],
        )


class LigAudioSearcher(BaseSearcher):
    BASE_URL = "https://web.ligaudio.ru/mp3"

    @classmethod
    def find_song(cls, song_name: str) -> list[Track]:
        try:
            r = requests.get(
                f"{cls.BASE_URL}/{song_name}", timeout=settings.searcher.request_timeout
            )
        except requests.exceptions.Timeout:
            return []

        bs = BeautifulSoup(r.text, features="html.parser")
        tracks = bs.find_all("div", {"class": "item"})

        track_list = []
        for i, track in enumerate(tracks):
            try:
                track_list.append(cls.parse_one_el(track))
            except Exception as e:
                logger.exception(
                    f"{cls.__name__}: For song '{song_name}': failed to parse {i} element"
                )

        return track_list

    @classmethod
    def parse_one_el(cls, el):
        return Track(
            title=el.find("span", {"class": "title"}).text.strip(),
            artist=el.find("span", {"class": "autor"}).text,
            length=el.find("span", {"class": "d"}).text,
            download_url="https:" + el.find("a", {"class": "down"})["href"],
        )


class AggregatedSortingSearcher:
    searchers = (HitmoLolSearcher, LigAudioSearcher, HitmoSearcher)

    def find_song(self, song_name: str) -> list[Track]:
        futures = []
        with ThreadPoolExecutor(max_workers=len(self.searchers)) as pool:
            for engine in self.searchers:
                futures.append(pool.submit(engine.find_song, song_name))

        results = reduce(list.__add__, (future.result() for future in futures))
        return sorted_tracks(results, song_name)


def get_track_by_songname(songname) -> Track | None:
    searcher = AggregatedSortingSearcher()
    tracks = searcher.find_song(songname)

    if not tracks:
        return None

    track = tracks[0]
    r = requests.get(track.download_url, stream=True)

    if r.status_code != 200:
        r.close()
        logger.error(
            f"Unable to download track: HTTP {r.status_code}\n  URL: {track.download_url}\n\n{r.content}"
        )
        # return f"Unable to download {songname.msg}. Error {r.status_code}"
        return None

    track.buf = io.BytesIO()
    track.buf.write(r.raw.read())
    track.buf.seek(0)
    r.close()
    return track


def get_track_by_url(url) -> t.Optional[Track]:
    opts = {
        "outtmpl": "yt",
        "logtostderr": True,
        "format": "mp3/bestaudio/best",
        "postprocessors": [
            {  # Extract audio using ffmpeg
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }
        ],
    }

    track_title = track_duration = ""
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        track_title = info.get("title", "N/A")
        track_duration = info.get("duration_string", "N/A")
        ydl.download(url)

    with open("yt.mp3", "br") as f:
        buf = io.BytesIO()
        buf.write(f.read())
        buf.seek(0)

    os.unlink("yt.mp3")

    return Track(
        artist="",
        title=track_title,
        length=track_duration,
        download_url=url,
        buf=buf,
    )


def get_track(songname_or_url) -> t.Optional[Track]:
    if songname_or_url.startswith("https://"):
        try:
            return get_track_by_url(songname_or_url)
        except Exception as e:
            logger.exception(e)
            return None

    return get_track_by_songname(songname_or_url)


def timetest(args):
    def test_threaded(timeout, out: list):
        settings.searcher.request_timeout = timeout
        searcher = AggregatedSortingSearcher()
        results = searcher.find_song(args.songname)
        out.extend(results)
        return results

    def test_unthreaded(timeout, out: list):
        settings.searcher.request_timeout = timeout
        results = []
        searchers = (HitmoLolSearcher, LigAudioSearcher, HitmoSearcher)
        for engine in searchers:
            results += engine.find_song(args.songname)
        results = sorted_tracks(results, args.songname)
        out.extend(results)
        return results

    outputs = [list() for _ in range(4)]
    tests = {
        "Threaded (timeout=2)": timeit.timeit(
            partial(test_threaded, 2, outputs[0]), number=1
        ),
        "Threaded (timeout=1)": timeit.timeit(
            partial(test_threaded, 1, outputs[1]), number=1
        ),
        "Unthreaded (timeout=2)": timeit.timeit(
            partial(test_unthreaded, 2, outputs[2]), number=1
        ),
        "Unthreaded (timeout=1)": timeit.timeit(
            partial(test_unthreaded, 1, outputs[3]), number=1
        ),
    }

    for k, v in sorted(tests.items(), key=lambda x: x[1]):
        print(f"{v:.2f} - {k}")

    for i, output in enumerate(outputs):
        print(f"Output {i} - {len(output)} items")

    # for i, t in enumerate(result):
    # print(f"{i}: {t.artist} - {t.title}\t\t{t.download_url}")


def youtube_test(args):
    opts = {
        "outtmpl": "yt",
        "logtostderr": True,
        "format": "mp3/bestaudio/best",
        "postprocessors": [
            {  # Extract audio using ffmpeg
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }
        ],
    }

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(args.url, download=False)
        print(info["title"])

    with YoutubeDL(opts) as ydl:
        ydl.download(args.url)


if __name__ == "__main__":
    import argparse
    import timeit
    from functools import partial

    p = argparse.ArgumentParser()
    subparsers = p.add_subparsers()

    p_timetest = subparsers.add_parser("timetest")
    p_timetest.add_argument("songname")
    p_timetest.set_defaults(func=timetest)

    p_youtube_test = subparsers.add_parser("youtube_test")
    p_youtube_test.add_argument("url")
    p_youtube_test.set_defaults(func=youtube_test)

    args = p.parse_args()
    args.func(args)
