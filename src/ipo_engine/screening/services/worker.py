"""
Queue workers: claim waiting documents from the database and process them.

Run inside the API process (``JOB_MODE=queue`` with ``WORKER_THREADS`` above zero) or on their own
with ``ipo worker``. Each thread claims one job at a time with a conditional update, so any number
of workers on any number of machines can share one database without taking the same job twice. A
worker that dies stops renewing its lease and the job is handed back (see
``DocumentService.requeue_expired``).
"""

from __future__ import annotations

import logging
import os
import platform
import threading
import time

from ipo_engine.screening.services.documents import DocumentService

logger = logging.getLogger(__name__)
POLL_S = 2.0
SWEEP_S = 15.0


class QueueWorker:
    def __init__(self, documents: DocumentService, threads: int, *, poll_s: float = POLL_S) -> None:
        self._docs = documents
        self._threads = threads
        self._poll = poll_s
        self._stop = threading.Event()
        self._pool: list[threading.Thread] = []
        self._name = f"{platform.node()}:{os.getpid()}"

    def start(self) -> None:
        for n in range(self._threads):
            t = threading.Thread(
                target=self._loop, args=(n,), name=f"queue-worker-{n}", daemon=True
            )
            t.start()
            self._pool.append(t)
        sweeper = threading.Thread(target=self._sweep, name="queue-sweeper", daemon=True)
        sweeper.start()
        self._pool.append(sweeper)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._docs.wake.set()
        for t in self._pool:
            t.join(timeout)

    def _loop(self, n: int) -> None:
        who = f"{self._name}/{n}"
        while not self._stop.is_set():
            try:
                doc_id = self._docs.claim_next(who)
            except Exception:  # a database blip must not kill the worker
                logger.exception("queue_claim_failed")
                self._stop.wait(self._poll)
                continue
            if doc_id is None:
                self._docs.wake.wait(self._poll)
                self._docs.wake.clear()
                continue
            try:
                self._docs.process(doc_id, worker=who, claimed=True)
            except Exception:
                logger.exception("queue_job_crashed", extra={"document_id": doc_id})

    def _sweep(self) -> None:
        while not self._stop.wait(SWEEP_S):
            try:
                self._docs.requeue_expired()
                sweep = getattr(self._docs.rate_limiter, "sweep", None)
                if sweep is not None:
                    sweep()
            except Exception:
                logger.exception("queue_sweep_failed")


def run_forever(documents: DocumentService, threads: int) -> None:
    """Block until interrupted (used by ``ipo worker``)."""
    worker = QueueWorker(documents, threads)
    worker.start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        worker.stop()
