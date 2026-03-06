from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _ensure_mysql_database_exists() -> None:
    if settings.DB_DIALECT.lower() != "mysql" or settings.DATABASE_URL:
        return
    try:
        import pymysql

        conn = pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            charset=settings.DB_CHARSET,
            autocommit=True,
        )
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.DB_NAME}` "
                f"CHARACTER SET {settings.DB_CHARSET} COLLATE {settings.DB_CHARSET}_general_ci"
            )
        conn.close()
    except Exception:
        # Keep startup resilient; main app will surface connection errors later if any.
        pass


_ensure_mysql_database_exists()

engine = create_engine(
    settings.sqlachemy_database_url,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
