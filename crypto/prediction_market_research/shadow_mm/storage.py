import gzip
import io
import json
import os
import queue
import threading
from pathlib import Path
from typing import Any, Dict, Optional


class JsonlEventWriter:
    """Non-blocking producer queue with a single durable append worker."""

    def __init__(
        self,
        path: Path,
        fsync_every: int = 5000,
        queue_max_events: int = 100000,
        gzip_compresslevel: int = 1,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._raw_handle = None
        self._compressor = None
        if self.path.suffix == ".gz":
            self._raw_handle = self.path.open("ab")
            self._compressor = gzip.GzipFile(
                filename="",
                mode="ab",
                fileobj=self._raw_handle,
                compresslevel=max(min(int(gzip_compresslevel), 9), 0),
            )
            self._handle = io.TextIOWrapper(
                self._compressor, encoding="utf-8", newline="\n"
            )
        else:
            self._handle = self.path.open("a", encoding="utf-8", buffering=1)
        self._metrics_lock = threading.Lock()
        self._written = 0
        self._enqueued = 0
        self._dropped = 0
        self._queue_high_water = 0
        self._closed = False
        self._worker_error: Optional[str] = None
        self._fsync_every = max(int(fsync_every), 0)
        self._sentinel = object()
        self._queue: queue.Queue = queue.Queue(maxsize=max(int(queue_max_events), 1))
        self._worker = threading.Thread(
            target=self._run_writer,
            name="jsonl-event-writer",
            daemon=True,
        )
        self._worker.start()

    def write(self, event: Dict[str, Any]) -> None:
        with self._metrics_lock:
            if self._closed:
                raise RuntimeError("cannot write to a closed event writer")
            worker_error = self._worker_error
        if worker_error:
            raise RuntimeError("event writer failed: {}".format(worker_error))
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            with self._metrics_lock:
                self._dropped += 1
            return
        with self._metrics_lock:
            self._enqueued += 1
            self._queue_high_water = max(
                self._queue_high_water, self._queue.qsize()
            )

    def _run_writer(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is self._sentinel:
                    return
                if self._worker_error is not None:
                    continue
                encoded = json.dumps(
                    item,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                self._handle.write(encoded + "\n")
                with self._metrics_lock:
                    self._written += 1
                    written = self._written
                if self._fsync_every and written % self._fsync_every == 0:
                    self._flush_durable()
            except BaseException as exc:
                with self._metrics_lock:
                    self._worker_error = "{}: {}".format(
                        type(exc).__name__, str(exc)[:500]
                    )
            finally:
                self._queue.task_done()

    def _flush_durable(self) -> None:
        self._handle.flush()
        if self._compressor is not None:
            self._compressor.flush()
        target = self._raw_handle if self._raw_handle is not None else self._handle
        target.flush()
        os.fsync(target.fileno())

    def close(self) -> None:
        with self._metrics_lock:
            if self._closed:
                return
            self._closed = True
        self._queue.put(self._sentinel)
        self._worker.join()
        if not self._handle.closed:
            self._flush_durable()
            self._handle.close()
        if self._raw_handle is not None and not self._raw_handle.closed:
            self._raw_handle.flush()
            os.fsync(self._raw_handle.fileno())
            self._raw_handle.close()
        if self._worker_error:
            raise RuntimeError("event writer failed: {}".format(self._worker_error))

    def drain(self) -> None:
        """Wait until all events enqueued so far have reached the file handle."""
        self._queue.join()
        if self._worker_error:
            raise RuntimeError("event writer failed: {}".format(self._worker_error))

    def summary(self) -> Dict[str, Any]:
        with self._metrics_lock:
            return {
                "events_enqueued_n": self._enqueued,
                "events_written_n": self._written,
                "events_dropped_n": self._dropped,
                "queue_high_water_n": self._queue_high_water,
                "queue_pending_n": self._queue.qsize(),
                "worker_error": self._worker_error,
            }

    def __enter__(self) -> "JsonlEventWriter":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> Optional[bool]:
        self.close()
        return None
