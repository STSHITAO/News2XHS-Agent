from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.job_service import JobService
from app.services.news_service import NewsService


class SchedulerService:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self.started = False

    def start(self) -> None:
        if not settings.SCHEDULER_ENABLED or self.started:
            return
        self.scheduler.add_job(
            self._fetch_hot_news_job,
            trigger="interval",
            minutes=max(1, settings.HOT_NEWS_INTERVAL_MINUTES),
            id="fetch_hot_news",
            replace_existing=True,
        )
        self.scheduler.start()
        self.started = True

    def stop(self) -> None:
        if self.started:
            self.scheduler.shutdown(wait=False)
            self.started = False

    def _fetch_hot_news_job(self) -> None:
        db = SessionLocal()
        try:
            job_service = JobService(db)
            run = job_service.start("fetch_hot_news", "Scheduler triggered hot-news fetch.")
            service = NewsService(db)
            bundle = service.fetch_and_store_hot_news(
                query=settings.HOT_NEWS_DEFAULT_QUERY,
                limit=settings.HOT_NEWS_DEFAULT_LIMIT,
                period="24h",
            )
            job_service.finish(run, "succeeded", f"Fetched {len(bundle.items)} items via {bundle.provider}.")
        except Exception as exc:
            try:
                job_service = JobService(db)
                run = job_service.start("fetch_hot_news", "Scheduler run failed before completion.")
                job_service.finish(run, "failed", str(exc))
            except Exception:
                pass
        finally:
            db.close()

