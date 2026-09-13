"""Client-side network connection used by the TUI. Runs a background
reader thread and exposes incoming messages through a thread-safe queue so
the curses main loop can poll it without blocking on I/O.
"""
import queue
import socket
import threading

from .protocol import LineReader, send


class ClientConnection:
    def __init__(self, host, port, timeout=5.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(None)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.incoming = queue.Queue()
        self._alive = True
        threading.Thread(target=self._reader_loop, daemon=True).start()

    def _reader_loop(self):
        reader = LineReader(self.sock)
        try:
            while True:
                for msg in reader.read_messages():
                    self.incoming.put(msg)
        except (ConnectionError, OSError):
            pass
        finally:
            self._alive = False
            self.incoming.put({"type": "_connection_lost"})

    def send(self, msg):
        try:
            send(self.sock, msg)
        except OSError:
            self._alive = False

    def poll(self):
        """Return a list of all messages received since the last poll."""
        out = []
        while True:
            try:
                out.append(self.incoming.get_nowait())
            except queue.Empty:
                break
        return out

    @property
    def alive(self):
        return self._alive

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
