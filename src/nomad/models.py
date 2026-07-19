from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


class Category(str, Enum):
    SEGURIDAD = "seguridad"
    DESARROLLO_CANTONAL = "desarrollo_cantonal"
    POLITICA = "politica"
    ECONOMIA = "economia"
    OTRO = "otro"


class Confidence(str, Enum):
    ALTO = "alto"
    MEDIO = "medio"
    BAJO = "bajo"


class SourceType(str, Enum):
    RSS = "rss"
    API = "api"
    MANUAL = "manual"


class NewsItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    summary: str = ""
    url: str
    source: str
    source_type: SourceType = SourceType.RSS
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    category: Category = Category.OTRO
    category_scores: dict[str, float] = Field(default_factory=dict)
    keywords: list[str] = Field(default_factory=list)
    stats_mentions: list[str] = Field(default_factory=list)
    topic_key: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class HardDataPoint(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    value: float | str | None = None
    unit: str = ""
    period: str = ""
    source: str
    url: str = ""
    category: Category = Category.ECONOMIA
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    meta: dict[str, Any] = Field(default_factory=dict)


class AnalysisDecision(BaseModel):
    sufficient_info: bool
    interesting: bool
    confidence: Confidence
    confidence_score: float = 0.0
    selected_news_ids: list[str] = Field(default_factory=list)
    selected_data_ids: list[str] = Field(default_factory=list)
    theme: str = ""
    category: Category = Category.OTRO
    narrative_angle: str = ""
    non_obvious_insight: str = ""
    gaps: list[str] = Field(default_factory=list)
    reasoning: str = ""


class DraftPost(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    week_label: str = ""
    category: Category = Category.OTRO
    theme: str = ""
    confidence: Confidence = Confidence.BAJO
    confidence_score: float = 0.0
    analysis_md: str = ""
    linkedin_post: str = ""
    sources: list[dict[str, str]] = Field(default_factory=list)
    news_ids: list[str] = Field(default_factory=list)
    data_ids: list[str] = Field(default_factory=list)
    decision: AnalysisDecision | None = None
    markdown_path: str = ""


class PublishedRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    published_at: datetime = Field(default_factory=datetime.utcnow)
    theme: str
    category: Category
    topic_keys: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    draft_id: str = ""
    notes: str = ""


class Catalog(BaseModel):
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    news: list[NewsItem] = Field(default_factory=list)
    hard_data: list[HardDataPoint] = Field(default_factory=list)
