"""One-connection TCP proxies for deterministic, real socket fault experiments."""

import http.client
import socket
import threading
from contextlib import contextmanager
from urllib.parse import urlsplit


DEADLINE = 10


def wait(event):
    if not event.wait(DEADLINE):
        raise TimeoutError("proxy barrier was not reached")


def relay(source, destination):
    try:
        while data := source.recv(65536):
            destination.sendall(data)
    except OSError:
        pass
    finally:
        try:
            destination.shutdown(socket.SHUT_WR)
        except OSError:
            pass


@contextmanager
def proxy(target, handler):
    """Run one bounded TCP session and propagate unexpected proxy failures."""
    failures = []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(DEADLINE)

        def serve():
            try:
                client, _ = listener.accept()
                with client, socket.create_connection(target, DEADLINE) as server:
                    client.settimeout(DEADLINE)
                    handler(client, server)
            except Exception as exc:
                failures.append(exc)

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        try:
            yield listener.getsockname()[1]
        finally:
            worker.join(DEADLINE + 1)
            if worker.is_alive():
                raise TimeoutError("proxy did not stop")
            if failures:
                raise failures[0]


class PutWire:
    """Hold a real PUT tail, hold its response, or interrupt upstream mid-body."""

    def __init__(self, mode):
        self.mode = mode
        self.reached = threading.Event()
        self.release = threading.Event()
        self.client_disconnected = threading.Event()
        self.result = None

    def __call__(self, client, server):
        reader = client.makefile("rb")
        with reader:
            lines = [reader.readline()]
            while (line := reader.readline()) != b"\r\n":
                if not line:
                    raise EOFError("incomplete PUT headers")
                lines.append(line)
            size = next(int(line.split(b":", 1)[1]) for line in lines
                        if line.lower().startswith(b"content-length:"))
            body = reader.read(size)
            if len(body) != size or size < 2:
                raise ValueError("incomplete synthetic PUT")
        server.sendall(b"".join(lines) + b"\r\n" + body[:1])
        watcher = threading.Thread(target=self.watch_client, args=(client,), daemon=True)
        watcher.start()
        if self.mode in {"tail", "upstream_eof"}:
            self.reached.set()
            wait(self.release)
        if self.mode == "upstream_eof":
            server.shutdown(socket.SHUT_WR)
        else:
            server.sendall(body[1:])
        response = http.client.HTTPResponse(server)
        response.begin()
        response.read()
        self.result = (response.status, response.getheader("x-amz-version-id"))
        if self.mode == "response":
            self.reached.set()
            wait(self.release)
        # Client outcome is its own timeout or process termination, not a fabricated response.
        wait(self.client_disconnected)
        watcher.join(DEADLINE)

    def watch_client(self, client):
        try:
            if client.recv(1) == b"":
                self.client_disconnected.set()
        except ConnectionResetError:
            self.client_disconnected.set()


def send_put(port, url, body, timeout):
    """Send one presigned, fixed-length request without HTTP retries."""
    target = urlsplit(url)
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.putrequest("PUT", target.path + "?" + target.query, skip_host=True)
        connection.putheader("Host", target.netloc)
        connection.putheader("Content-Length", str(len(body)))
        connection.endheaders(body)
        return connection.getresponse().status
    finally:
        connection.close()


class CommitWire:
    """Suppress PostgreSQL's genuine COMMIT response on an established TCP session."""

    def __init__(self):
        self.withheld = threading.Event()
        self.disconnect = threading.Event()

    def __call__(self, client, server):
        forward = threading.Thread(target=relay, args=(client, server), daemon=True)
        forward.start()
        committed = False
        with server.makefile("rb") as stream:
            while kind := stream.read(1):
                length = stream.read(4)
                if len(length) != 4:
                    raise EOFError("incomplete PostgreSQL frame")
                payload = stream.read(int.from_bytes(length, "big") - 4)
                if kind == b"C" and payload == b"COMMIT\x00":
                    committed = True
                if committed and kind == b"Z":
                    assert payload == b"I"
                    self.withheld.set()
                    wait(self.disconnect)
                    client.shutdown(socket.SHUT_RDWR)
                    break
                if not committed:
                    client.sendall(kind + length + payload)
            else:
                raise EOFError("server disconnected before returning idle ReadyForQuery")
        forward.join(DEADLINE)
