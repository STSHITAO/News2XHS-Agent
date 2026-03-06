from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import JobRun


class JobService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def start(self, job_name: str, message: str = "") -> JobRun:
        run = JobRun(job_name=job_name, status="running", message=message)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def finish(self, run: JobRun, status: str, message: str = "") -> JobRun:
        run.status = status
        run.message = message
        run.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(run)
        return run

    def list_runs(self, limit: int = 100) -> list[JobRun]:
        stmt = select(JobRun).order_by(desc(JobRun.created_at)).limit(limit)
        return list(self.db.scalars(stmt).all())

