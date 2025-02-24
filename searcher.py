import os
import typing as t
import urllib
import urllib.parse
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from Levenshtein import distance

from logs import logger


@dataclass()
class Track:
    artist: str
    title: str
    length: str
    download_url: str

    requester: str = ''

    def get_filename(self):
        normalized_url = urllib.parse.unquote(self.download_url)
        urlpath = urllib.parse.urlsplit(normalized_url).path
        return os.path.basename(urlpath)


def sorted_tracks(tracks: t.List[Track], song_name: str) -> t.List:
    sorter = lambda track: distance(f"{track.artist} {track.title}", song_name, processor=str.lower)
    return list(sorted(tracks, key=sorter))


class BaseSearcher:
    pass


class HitmoSearcher(BaseSearcher):
    BASE_URL = "https://rus.hitmotop.com"

    @classmethod
    def find_song(cls, song_name: str) -> t.List[Track]:
        song_name_a = "+".join(song_name.split())
        url = f"{cls.BASE_URL}/search?q={song_name_a}"
        r = requests.get(url)

        bs = BeautifulSoup(r.text, features="html.parser")
        tracks = bs.find_all("li", {"class": "tracks__item"})

        track_list = []
        for i, track in enumerate(tracks):
            try:
                track_list.append(cls.parse_one_el(track))
            except Exception as e:
                logger.error(
                    f"{cls.__name__}: For song '{song_name}': failed to parse {i} element: {e}"
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


class LigAudioSearcher(BaseSearcher):
    BASE_URL = "https://web.ligaudio.ru/mp3"

    @classmethod
    def find_song(cls, song_name: str) -> t.List[Track]:
        r = requests.get(f"{cls.BASE_URL}/{song_name}")

        bs = BeautifulSoup(r.text, features="html.parser")
        tracks = bs.find_all("div", {"class": "item"})

        track_list = []
        for i, track in enumerate(tracks):
            try:
                track_list.append(cls.parse_one_el(track))
            except Exception as e:
                logger.error(
                    f"{cls.__name__}: For song '{song_name}': failed to parse {i} element: {e}"
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
    searchers = (LigAudioSearcher, HitmoSearcher)

    def find_song(self, song_name: str) -> t.List[Track]:
        results = []
        for engine in self.searchers:
            results += engine.find_song(song_name)
        return sorted_tracks(results, song_name)



if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("songname")
    args = p.parse_args()

    results = []
    searchers = (LigAudioSearcher, HitmoSearcher)

    for engine in searchers:
        results += engine.find_song(args.songname)

    result = sorted_tracks(results, args.songname)

    for i, t in enumerate(result):
        print(f"{i}: {t.artist} - {t.title}\t\t{t.download_url}")
