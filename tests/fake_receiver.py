#!/usr/bin/env python3
"""Local-only stateful receiver. Every socket accepts exactly one CR command."""
import argparse
import socket
import socketserver
import struct
import threading
import time


class Receiver(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, power="PWON", volume=10, mute="MUOFF", port=0):
        super().__init__(("127.0.0.1", port), Handler)
        self.power, self.volume, self.mute = power, volume, mute
        self.commands, self.transactions = [], []
        self.lock = threading.Lock()
        self.responses = {}
        self.no_ack = False
        self.fragment = False
        self.never_on = False
        self.on_after_queries = 0
        self.pending_on = None
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.shutdown()
        self.server_close()
        self.thread.join()

    def reply(self, command):
        with self.lock:
            self.commands.append(command)
            if command == "PW?":
                if self.pending_on is not None:
                    if self.pending_on == 0:
                        self.power, self.pending_on = "PWON", None
                    else:
                        self.pending_on -= 1
                reply = self.power
            elif command == "PWON":
                if not self.never_on:
                    if self.on_after_queries:
                        self.pending_on = self.on_after_queries
                    else:
                        self.power = "PWON"
                reply = self.power
            elif command == "PWSTANDBY":
                self.power, self.pending_on = "PWSTANDBY", None
                reply = self.power
            elif command == "MV?":
                reply = "MV{:02d}".format(self.volume)
            elif command in ("MVUP", "MVDOWN"):
                if self.power == "PWON":
                    self.volume += 1 if command == "MVUP" else -1
                reply = "MV{:02d}".format(self.volume)
            elif command.startswith("MV") and command[2:].isdigit():
                self.volume = int(command[2:])
                reply = "MV{:02d}".format(self.volume)
            elif command == "MU?":
                reply = self.mute
            elif command in ("MUON", "MUOFF"):
                self.mute = command
                reply = self.mute
            elif command == "SI?":
                reply = "SINET"
            else:
                reply = "UNKNOWN"
            if command in self.responses:
                return self.responses[command]
            if self.no_ack and not command.endswith("?"):
                return None
            return reply.encode("ascii") + b"\r"


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        wire = bytearray()
        try:
            while b"\r" not in wire:
                chunk = self.request.recv(1024)
                if not chunk:
                    return
                wire.extend(chunk)
            command, _, extra = wire.partition(b"\r")
            reply = self.server.reply(command.decode("ascii"))
            transaction = {"wire": bytes(wire), "extra": bytes(extra), "closed": False}
            self.server.transactions.append(transaction)
            if reply == "reset":
                self.request.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                # Close here: socketserver's normal shutdown_request first sends
                # an orderly FIN, defeating the intended abortive close on macOS.
                self.request.close()
                return
            if reply == "trickle":
                for _ in range(40):
                    self.request.sendall(b"P")
                    time.sleep(0.02)
            elif reply is not None:
                if self.server.fragment:
                    for byte in reply:
                        self.request.sendall(bytes([byte]))
                        time.sleep(0.002)
                else:
                    self.request.sendall(reply)
            # Deliberately keep the socket open, just like a persistent receiver.
            # The client must close it, including when no acknowledgement exists.
            while True:
                chunk = self.request.recv(1024)
                if not chunk:
                    transaction["closed"] = True
                    return
                transaction["extra"] += chunk
        except (OSError, UnicodeError):
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=2323)
    parser.add_argument("--standby", action="store_true")
    args = parser.parse_args()
    with Receiver(power="PWSTANDBY" if args.standby else "PWON", port=args.port) as server:
        print("Fake Marantz listening on 127.0.0.1:{}".format(server.server_address[1]), flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
