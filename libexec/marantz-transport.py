#!/usr/bin/env python3
"""One bounded TCP transaction; standard library only, no command replay."""

import signal
import socket
import sys


class Deadline(Exception):
    pass


def expired(_signum, _frame):
    raise Deadline()


def main():
    host, port, command, mode, prefix, connect_timeout, response_timeout = sys.argv[1:]
    signal.signal(signal.SIGALRM, expired)
    sock = None
    sent = False
    phase = "connect"
    pending = bytearray()
    try:
        # SIGALRM also bounds DNS resolution and the sum of address attempts.
        signal.setitimer(signal.ITIMER_REAL, float(connect_timeout))
        sock = socket.create_connection((host, int(port)), float(connect_timeout))
        phase = "send"
        signal.setitimer(signal.ITIMER_REAL, float(response_timeout))
        sock.settimeout(float(response_timeout))
        sock.sendall(command.encode("ascii") + b"\r")
        sent = True
        phase = "receive"
        received = 0
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                if pending:
                    raise ValueError("incomplete response (missing CR)")
                if mode == "optional":
                    return 0
                raise ValueError("connection closed without a matching response")
            received += len(chunk)
            if received > 8192:
                raise ValueError("response exceeds 8192 bytes")
            pending.extend(chunk)
            while b"\r" in pending:
                line, _, tail = pending.partition(b"\r")
                pending = bytearray(tail.lstrip(b"\n"))
                line = line.lstrip(b"\n")  # tolerate CRLF alongside verified CR
                if not line:
                    continue
                if any(byte < 32 or byte > 126 for byte in line):
                    raise ValueError("non-printable bytes in response")
                response = line.decode("ascii")
                # An MV namespace advisory is not the current numeric volume.
                # Do not turn a maximum/limit notification into the volume value.
                if prefix == "MV" and response.startswith("MV "):
                    continue
                if mode == "raw" or response.startswith(prefix):
                    print(response)
                    return 0
    except (Deadline, socket.timeout):
        if sent and mode == "optional":
            if pending:
                print("marantz: incomplete response (missing CR); command may have taken effect.", file=sys.stderr)
                return 1
            return 0  # setters are allowed to have no acknowledgement
        if phase == "send":
            print("marantz: send timeout; command may have taken effect.", file=sys.stderr)
        elif sent:
            message = "response timeout; command may have taken effect" if mode == "raw" else "response timeout"
            print("marantz: " + message + ".", file=sys.stderr)
        else:
            print("marantz: Marantz at {} is unreachable (connection timeout).".format(host), file=sys.stderr)
        return 1
    except (OSError, ValueError, UnicodeError) as error:
        if sock is None:
            print("marantz: Marantz at {} is unreachable: {}.".format(host, error), file=sys.stderr)
        else:
            suffix = "; command may have taken effect" if mode in ("optional", "raw") else ""
            print("marantz: transport failed: {}{}.".format(error, suffix), file=sys.stderr)
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if sock is not None:
            sock.close()


if __name__ == "__main__":
    sys.exit(main())
