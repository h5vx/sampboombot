import logging
import os
import shutil
from queue import Queue

import requests

from config import settings
from icefeeder import IceConfig, IceFeeder
from messageserv import SongRequestItem, create_server, song_requests_queue
from searcher import AggregatedSortingSearcher, Track

logger = logging.getLogger(__name__)

TRACKS_DOWNLOAD_PATH = "./tracks"

def handle_song_request_to_file(q: Queue, sr: SongRequestItem) -> str:
    songfinder = AggregatedSortingSearcher()
    tracks: list[Track] = songfinder.find_song(sr.msg)

    if len(tracks) == 0:
        return f"Track not found: {sr.msg}"

    track = tracks[0]

    track_path = os.path.join(TRACKS_DOWNLOAD_PATH, track.get_filename())
    if os.path.exists(track_path):
        q.put(track_path)

        if q.qsize() == 1:
            return f"Queued* next: {track.artist} - {track.title} from {sr.nick}"
        return f"Queue* #{q.qsize() + 1}: {track.artist} - {track.title} from {sr.nick}"

    r = requests.get(track.download_url, stream=True)

    if r.status_code != 200:
        logger.error(f"Unable to download track: HTTP {r.status_code}\n  URL: {track.download_url}\n\n{r.content}")
        return f"Unable to download {sr.msg}. Error {r.status_code}"

    with open(track_path, "wb") as f:
        shutil.copyfileobj(r.raw, f)
    
    q.put(track)

    if q.qsize() == 1:
        return f"Queued next: {track.artist} - {track.title} from {sr.nick}"
    return f"Queue #{q.qsize() + 1}: {track.artist} - {track.title} from {sr.nick}"


def handle_song_request_to_ice(q: Queue, sr: SongRequestItem) -> str:
    songfinder = AggregatedSortingSearcher()
    tracks: list[Track] = songfinder.find_song(sr.msg)

    if len(tracks) == 0:
        return f"Track not found: {sr.msg}"
    
    track = tracks[0]

    r = requests.get(track.download_url, stream=True)
    if r.status_code != 200:
        r.close()
        logger.error(f"Unable to download track: HTTP {r.status_code}\n  URL: {track.download_url}\n\n{r.content}")
        return f"Unable to download {sr.msg}. Error {r.status_code}"
    r.close()

    track.requester = sr.nick
    q.put(track)

    if q.qsize() == 1:
        return f"Queued next: {track.artist} - {track.title}"
    return f"Queue #{q.qsize() + 1}: {track.artist} - {track.title}"


def main():
    iceconf = IceConfig(**settings.icecast_client)
    ice = IceFeeder(iceconf)

    if not ice.connect_to_icecast():
        logger.error("Coludn't connect to icecast")
        return
    
    ice.start()

    logger.info("Starting message server")
    msgsrv_addr = (settings.message_server.listen_addr, settings.message_server.listen_port)
    msgsrv, msgsrv_thread = create_server(msgsrv_addr)
    msgsrv_thread.start()
    logger.info(f"Message server running on {msgsrv_addr[0]}:{msgsrv_addr[1]}")

    logger.info("Everything is working. Waiting messages...")

    try:
        while True:
            song_request: SongRequestItem = song_requests_queue.get()

            if song_request.is_skip_request:
                ice.skip_current()
                continue

            msg = handle_song_request_to_ice(ice.track_queue, song_request)
            song_request.response.put(msg)
    except KeyboardInterrupt:
        logger.info("Shutdown!")
        msgsrv.shutdown()
        msgsrv_thread.join()

        ice.shutdown()
        ice.join()


if __name__ == "__main__":
    main()