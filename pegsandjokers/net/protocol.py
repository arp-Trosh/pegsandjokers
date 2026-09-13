"""Wire protocol: newline-delimited JSON messages over a TCP socket."""
import json
import socket


def encode(msg: dict) -> bytes:
    return (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")


class LineReader:
    """Buffers bytes from a socket and yields complete decoded JSON messages."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = b""

    def read_messages(self):
        """Blocking read of one recv() worth of data; yields zero or more
        decoded message dicts. Raises ConnectionError on EOF."""
        chunk = self.sock.recv(4096)
        if not chunk:
            raise ConnectionError("peer closed connection")
        self.buf += chunk
        out = []
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            if line.strip():
                out.append(json.loads(line.decode("utf-8")))
        return out


def send(sock: socket.socket, msg: dict):
    sock.sendall(encode(msg))
