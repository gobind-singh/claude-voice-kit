#!/usr/bin/env python3
"""Short-lived microphone recorder used by listend.

The microphone is only ever opened inside this process, and the process exits when recording
ends, so macOS always releases the mic (and its orange indicator) afterwards, even if something
goes wrong in the service.

  recorder.py <device-json> <max-seconds>
stdin:  waits for a line "start" (EOF before that: exit without touching the mic);
        then records until a line "stop", stdin EOF (the service went away) or max-seconds (0 = no limit).
stdout: raw 16 kHz mono float32 samples, in blocks of 30 ms.
"""
import json, os, queue, sys, threading

RATE, BLOCK = 16000, 480


def main():
    device = json.loads(sys.argv[1]) if len(sys.argv) > 1 else None
    max_s = float(sys.argv[2]) if len(sys.argv) > 2 else 0
    import sounddevice as sd                       # imported up front: start is instant later
    if sys.stdin.readline().strip() != "start":
        return
    q = queue.Queue()
    stop = threading.Event()

    def cb(indata, frames, t, status):
        q.put(indata[:, 0].tobytes())

    def writer():
        out = sys.stdout.buffer
        while True:
            b = q.get()
            if b is None:
                break
            try:
                out.write(b)
                out.flush()
            except (BrokenPipeError, OSError):
                stop.set()
                break

    def watch_stdin():
        sys.stdin.readline()                       # "stop" or EOF
        stop.set()

    w = threading.Thread(target=writer, daemon=True)
    w.start()
    threading.Thread(target=watch_stdin, daemon=True).start()
    s = sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK, callback=cb, device=device)
    s.start()
    stop.wait(max_s if max_s > 0 else None)
    q.put(None)                                    # hand over the audio first (fast)…
    w.join(2)
    try:
        sys.stdout.buffer.close()
    except OSError:
        pass
    s.abort()                                      # …then release the microphone
    s.close()
    os._exit(0)                                    # process ends: microphone released by macOS


if __name__ == "__main__":
    main()
