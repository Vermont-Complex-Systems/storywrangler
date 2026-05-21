"""Health check result model — one row per probe attempt."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Float, Index, String, Text
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel


class HealthCheck(SQLModel, table=True):
    """One health-check probe result for a registered dataset."""

    __tablename__ = "health_checks"
    __table_args__ = (
        Index("ix_health_checks_lookup", "domain", "dataset_id", "checked_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    domain: str = Field(sa_column=Column(String, nullable=False))
    dataset_id: str = Field(sa_column=Column(String, nullable=False))
    status: str = Field(sa_column=Column(String, nullable=False))
    latency_ms: Optional[float] = Field(default=None, sa_column=Column(Float))
    error: Optional[str] = Field(default=None, sa_column=Column(Text))
    checked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
