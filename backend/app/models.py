import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AdminUnit(Base):
    __tablename__ = "admin_units"
    __table_args__ = (
        CheckConstraint(
            "admin_level in ('province','district','municipality','ward')",
            name="ck_admin_units_level",
        ),
        Index("idx_admin_units_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name_en: Mapped[str] = mapped_column(String(200))
    name_ne: Mapped[str | None] = mapped_column(String(200))
    admin_level: Mapped[str] = mapped_column(String(20), index=True)
    parent_code: Mapped[str | None] = mapped_column(String(50), index=True)
    population: Mapped[int | None] = mapped_column(Integer)
    geom = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
    )


class WardRiskProfile(Base):
    __tablename__ = "ward_risk_profiles"

    unit_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("admin_units.unit_code"), primary_key=True
    )
    flood_score: Mapped[float | None] = mapped_column(Float)
    landslide_score: Mapped[float | None] = mapped_column(Float)
    earthquake_score: Mapped[float | None] = mapped_column(Float)
    river_distance_m: Mapped[float | None] = mapped_column(Float)
    mean_slope_deg: Mapped[float | None] = mapped_column(Float)
    impervious_surface_pct: Mapped[float | None] = mapped_column(Float)
    indicator_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DisasterIncident(Base):
    __tablename__ = "disaster_incidents"
    __table_args__ = (
        Index("idx_incidents_location", "location", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True)
    hazard_type: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(Text)
    incident_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    unit_code: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("admin_units.unit_code"), index=True
    )
    deaths: Mapped[int] = mapped_column(Integer, default=0)
    injured: Mapped[int] = mapped_column(Integer, default=0)
    families_affected: Mapped[int] = mapped_column(Integer, default=0)
    estimated_loss_npr: Mapped[int] = mapped_column(BigInteger, default=0)
    location = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)


class CitizenReport(Base):
    __tablename__ = "citizen_reports"
    __table_args__ = (
        CheckConstraint(
            "ai_severity is null or ai_severity in ('low','moderate','high','critical')",
            name="ck_reports_severity",
        ),
        CheckConstraint(
            "status in ('pending','verified','dispatched','resolved')",
            name="ck_reports_status",
        ),
        Index("idx_reports_location", "location", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unit_code: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("admin_units.unit_code"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    location = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=False
    )
    ai_hazard_category: Mapped[str | None] = mapped_column(String(50))
    ai_severity: Mapped[str | None] = mapped_column(String(20))
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    ai_reasoning: Mapped[str | None] = mapped_column(Text)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DrrDocument(Base):
    __tablename__ = "drr_documents"
    __table_args__ = (
        CheckConstraint("language in ('en','ne')", name="ck_drr_language"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_code: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("admin_units.unit_code"), index=True
    )
    source_title: Mapped[str] = mapped_column(Text)
    section_ref: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(5))
    chunk_text: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(1536))
    