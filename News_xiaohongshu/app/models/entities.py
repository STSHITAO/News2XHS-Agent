from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class HotTopic(TimestampMixin, Base):
    __tablename__ = "hot_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str] = mapped_column(String(64), default="global")
    score: Mapped[int] = mapped_column(Integer, default=0)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["NewsItem"]] = relationship(back_populates="topic")


class NewsItem(TimestampMixin, Base):
    __tablename__ = "news_items"
    __table_args__ = (UniqueConstraint("url_key", name="uq_news_items_url_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("hot_topics.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(1024))
    url_key: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(64), default="unknown")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="")

    topic: Mapped[HotTopic | None] = relationship(back_populates="items")
    drafts: Mapped[list["Draft"]] = relationship(back_populates="seed_item")


class Draft(TimestampMixin, Base):
    __tablename__ = "xhs_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    cover_image_url: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    editor_notes: Mapped[str] = mapped_column(Text, default="")
    source_item_id: Mapped[int | None] = mapped_column(ForeignKey("news_items.id"), nullable=True)

    seed_item: Mapped[NewsItem | None] = relationship(back_populates="drafts")
    publish_tasks: Mapped[list["PublishTask"]] = relationship(back_populates="draft")


class PublishTask(TimestampMixin, Base):
    __tablename__ = "xhs_publish_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("xhs_drafts.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    request_payload: Mapped[str] = mapped_column(Text, default="")
    response_payload: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")

    draft: Mapped[Draft] = relationship(back_populates="publish_tasks")


class JobRun(TimestampMixin, Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    message: Mapped[str] = mapped_column(Text, default="")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
