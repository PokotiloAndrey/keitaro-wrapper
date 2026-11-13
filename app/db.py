from datetime import datetime, timezone
from sqlalchemy import create_engine, String, JSON, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


class Draft(Base):
    __tablename__ = "drafts"
    stream_id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int]
    baseline: Mapped[dict] = mapped_column(JSON)
    offers: Mapped[list] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(default=1)


class Operation(Base):
    __tablename__ = "operations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str]
    status: Mapped[str]
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
)
Session = sessionmaker(engine, expire_on_commit=False)
