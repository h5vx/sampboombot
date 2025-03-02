import logging
import socket
import socketserver
from dataclasses import dataclass
from queue import Queue
from threading import Thread

from config import settings

logger = logging.getLogger(__name__)

song_requests_queue = Queue(maxsize=1024)


def try_many(f, options):
    last_exception = None

    for o in options:
        try:
            return f(o)
        except Exception as e:
            last_exception = e

    raise last_exception


@dataclass
class SongRequestItem:
    nick: str
    msg: str
    response: Queue
    is_skip_request: bool = False


class MessageHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            nick_len = self.request.recv(1)[0]
            nick = self.request.recv(nick_len)
            nick = try_many(nick.decode, settings.message_server.in_encodings)

            msg_len = self.request.recv(1)[0]
            msg = self.request.recv(msg_len)
            msg = try_many(msg.decode, settings.message_server.in_encodings).strip()
        except Exception as e:
            logger.error(f"Malformed message from {self.client_address[0]}")
            logger.error(e)
            return
        
        logger.info(f"Song request from {nick} / {self.client_address[0]} - '{msg}'")

        if msg == "!skip":
            song_requests_queue.put(SongRequestItem(nick=nick, msg=msg, is_skip_request=True, response=None))
            self.request.sendall(b"OK")
            return

        response_q = Queue()

        song_requests_queue.put(SongRequestItem(nick=nick, msg=msg, response=response_q))
        response = response_q.get()
        response = try_many(response.encode, settings.message_server.out_encodings)

        self.request.sendall(response[:128])


def create_server(addr) -> tuple[socketserver.TCPServer, Thread]:
    server = socketserver.ThreadingTCPServer(addr, MessageHandler)
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def server_thread():
        server.serve_forever()
    
    return server, Thread(target=server_thread)


if __name__ == "__main__":
    from searcher import AggregatedSortingSearcher, Track

    listen_addr = ('127.0.0.1', 1234)
    server, server_thread = create_server(listen_addr)
    server_thread.start()

    print(f"We are listening on {listen_addr[0]}:{listen_addr[1]}")

    songfinder = AggregatedSortingSearcher()

    try:
        while True:
            item: SongRequestItem = song_requests_queue.get()
            track: Track = songfinder.find_song(item.msg)[0]
            item.response.put(f"{item.nick}: {track.artist} - {track.title} ({track.length}) - {track.get_filename()} - {track.download_url}")
            
    except KeyboardInterrupt:
        server.shutdown()
        server_thread.join()
    
