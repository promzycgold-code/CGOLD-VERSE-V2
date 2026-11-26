import time
import threading
from uuid import uuid4


class JobCancelled(Exception):
    pass


class JobManager:
    def __init__(self):
        self.jobs = {}
        self.lock = threading.RLock()

    def create(self):
        with self.lock:
            self.cleanup()

            job_id = uuid4().hex

            self.jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "stage": "Waiting to process",
                "progress": 0,
                "created_at": time.time(),
                "updated_at": time.time(),
                "finished_at": None,
                "cancel_requested": False,
                "result": None,
                "error": None,
            }

            return job_id

    def get(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)

            if job is None:
                return None

            data = job.copy()

            end = job["finished_at"] or time.time()

            data["elapsed"] = round(
                end - job["created_at"], 1
            )

            return data

    def update(self, job_id, stage, progress):
        with self.lock:
            job = self.jobs[job_id]

            if job["cancel_requested"]:
                raise JobCancelled()

            job["status"] = "processing"
            job["stage"] = stage
            job["progress"] = max(
                job["progress"],
                min(99, progress)
            )
            job["updated_at"] = time.time()

    def complete(self, job_id, result):
        with self.lock:
            job = self.jobs[job_id]

            if job["cancel_requested"]:
                self.mark_cancelled(job_id)
                return

            job["status"] = "completed"
            job["stage"] = "Processing complete"
            job["progress"] = 100
            job["result"] = result
            job["finished_at"] = time.time()
            job["updated_at"] = time.time()

    def fail(self, job_id, error):
        with self.lock:
            job = self.jobs[job_id]

            if job["cancel_requested"]:
                self.mark_cancelled(job_id)
                return

            job["status"] = "failed"
            job["stage"] = "Processing failed"
            job["error"] = str(error)
            job["finished_at"] = time.time()
            job["updated_at"] = time.time()

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)

            if job is None:
                return False

            if job["status"] not in (
                "queued", "processing"
            ):
                return False

            job["cancel_requested"] = True
            job["status"] = "cancelling"
            job["stage"] = "Cancellation requested"
            job["updated_at"] = time.time()

            return True

    def check_cancelled(self, job_id):
        with self.lock:
            if self.jobs[job_id]["cancel_requested"]:
                raise JobCancelled()

    def mark_cancelled(self, job_id):
        with self.lock:
            job = self.jobs[job_id]

            job["status"] = "cancelled"
            job["stage"] = "Processing cancelled"
            job["result"] = None
            job["finished_at"] = time.time()
            job["updated_at"] = time.time()

    def cleanup(self, max_age=1800):
        with self.lock:
            now = time.time()

            expired = [
                job_id
                for job_id, job in self.jobs.items()
                if job["finished_at"] is not None
                and now - job["finished_at"] > max_age
            ]

            for job_id in expired:
                del self.jobs[job_id]


job_manager = JobManager()