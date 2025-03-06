import io
import logging
import os
import threading
from dataclasses import dataclass, field
from queue import Queue

import requests
import shout

from searcher import Track

logger = logging.getLogger(__name__)

script_dir = os.path.dirname(os.path.realpath(__file__))
elevator_music_path = os.path.join(script_dir, "assets", "bardcore.mp3")


@dataclass
class IceConfig:
    host: str
    port: int
    user: str
    password: str
    mount: str
    format_: str
    protocol: str
    name: str = ""
    genre: str = ""
    url: str = ""
    public: int = 1
    chunk_size: int = 4096
    audio_info: dict = field(
        default_factory=lambda: {
            shout.SHOUT_AI_BITRATE: "256",
            shout.SHOUT_AI_SAMPLERATE: "48000",
            shout.SHOUT_AI_CHANNELS: "2",
        }
    )

    def set_bitrate(self, bitrate: str):
        self.audio_info[shout.SHOUT_AI_BITRATE] = bitrate

    def set_samplerate(self, samplerate: str):
        self.audio_info[shout.SHOUT_AI_SAMPLERATE] = samplerate

    def apply_to_shout_instance(self, s: shout.Shout):
        s.host = self.host
        s.port = self.port
        s.user = self.user
        s.password = self.password
        s.mount = self.mount
        s.format = self.format_
        s.protocol = self.protocol
        s.name = self.name
        s.genre = self.genre
        s.url = self.url
        s.public = self.public
        s.audio_info = self.audio_info


class IceFeeder(threading.Thread):
    n_connect_attempts = 10

    def __init__(self, config: IceConfig):
        self.s = shout.Shout()
        self.config = config

        self.config.apply_to_shout_instance(self.s)

        self.track_queue: Queue[Track] = Queue()
        self.working = False

        self.current_track = None

        self._skip_flag = False

        with open(elevator_music_path, "rb") as f:
            self._elevator_music = io.BytesIO(f.read())
        
        super().__init__()

    def connect_to_icecast(self):
        logger.info(f"Connecting to icecast server {self.s.host}:{self.s.port}")

        success = False

        for i in range(1, self.n_connect_attempts + 1):
            try:
                self.s.open()
                success = True
                break
            except SystemError as e:
                logger.info(f"SystemError. Retrying ({i})")
            except shout.ShoutException as e:
                logger.info(f"{e}? I guess it should work?")
                success = True
                break
            except AttributeError as e:
                self.s = shout.Shout()
                self.config.apply_to_shout_instance(self.s)
                logger.info(f"Recreate instance")

        if success:
            logger.info(f"Connected!")

        conn_result = self.s.get_connected()
        return success and conn_result == -7

    def shutdown(self):
        self.working = False

    def skip_current(self):
        self._skip_flag = True
    
    def update_meta(self):
        t = self.current_track

        if t is None:
            return

        songinfo = (
            f"{t.artist} - {t.title} ({t.length}) @{t.requester}"
            f" | {self.track_queue.qsize()} tracks in queue"
        )

        try:
            self.s.set_metadata({"song": songinfo})
        except Exception as e:
            logger.exception(str(e))

    def _feed_next_block(self, fp) -> bool:
        buf = fp.read(self.config.chunk_size)

        if len(buf) == 0:
            return False

        if len(buf) < self.config.chunk_size:
            self.s.send(buf)
            return False
        self.s.send(buf)
        self.s.sync()
        return True

    def run(self):
        self.working = True

        while self.working:
            logger.debug(f"Playing elevator music at pos {self._elevator_music.tell()}")

            if self.track_queue.empty():
                self.s.set_metadata({"song": "No songs in queue. Write !!play SONG NAME"})

            while self.working and self.track_queue.empty():
                if not self._feed_next_block(self._elevator_music):
                    logger.debug("Reset elevator buffer")
                    self._elevator_music.seek(0)
            
            if not self.working:
                self.s.close()
                return

            logger.debug(f"Get track from queue")

            self.current_track = self.track_queue.get()
            t = self.current_track
            self.update_meta()

            logger.info(f"Playing: {t.artist} - {t.title} ({t.length})")

            while not self._skip_flag and self._feed_next_block(t.buf):
                pass

            logger.debug(f"DONE Playing {t.artist} - {t.title} ({t.length})")

            self._skip_flag = False

        self.s.close()
