"""Run bounded independent queues while retaining each service's MySQL claim logic."""
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import logging
from time import monotonic, sleep

from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)


def run_queues(factory, workflows, heartbeat, concurrency):
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="career-queue") as pool:
        pending = deque(workflows)
        running = {}
        due = {}
        while True:
            heartbeat()
            now = monotonic()
            for _ in range(len(pending)):
                if len(running) >= concurrency:
                    break
                workflow = pending.popleft()
                if due.get(workflow, 0) <= now:
                    running[pool.submit(workflow, factory)] = workflow
                else:
                    pending.append(workflow)
            if not running:
                sleep(0.1)
                continue
            completed, _ = wait(running, timeout=0.1, return_when=FIRST_COMPLETED)
            for task in completed:
                workflow = running.pop(task)
                try:
                    delay = 0 if task.result() else 1
                except OperationalError:
                    logger.warning("queue database temporarily unavailable workflow=%s", workflow.__name__)
                    delay = 3
                except Exception as exc:
                    logger.error("queue execution failed workflow=%s type=%s", workflow.__name__, type(exc).__name__)
                    delay = 3
                due[workflow] = monotonic() + delay
                pending.append(workflow)
