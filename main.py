import logging
from queue import Queue
import sys
import signal

import requests

from config import settings
from icefeeder import IceConfig, IceFeeder
from messageserv import SongRequestItem, create_server, song_requests_queue
from searcher import get_track

logger = logging.getLogger(__name__)


def handle_song_request(q: Queue, sr: SongRequestItem) -> str:
    track = get_track(sr.msg)

    if not track:
        return f"Track not found: {sr.msg}"

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

    def sigterm_handler(sig, frame):
        logger.info("Shutdown!")
        msgsrv.shutdown()
        logger.info("Waiting message server to stop...")
        msgsrv_thread.join()
        ice.shutdown()
        logger.info("Waiting icefeeder to stop...")
        ice.join()
        logger.info("Shutdown complete")
        sys.exit(0)

    signal.signal(signal.SIGTERM, sigterm_handler)

    logger.info("Everything is working. Waiting messages...")

    try:
        while True:
            song_request: SongRequestItem = song_requests_queue.get()

            if song_request.is_skip_request:
                ice.skip_current()
                continue

            msg = handle_song_request(ice.track_queue, song_request)
            ice.update_meta()
            song_request.response.put(msg)
    except KeyboardInterrupt:
        logger.info("Shutdown!")
        msgsrv.shutdown()
        msgsrv_thread.join()

        ice.shutdown()
        ice.join()


if __name__ == "__main__":
    main()