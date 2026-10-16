from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class MlInsightRead(BaseModel):
    id: UUID
    asset_id: UUID | None
    asset_name: str | None
    work_order_id: UUID | None
    work_order_number: str | None
    insight_type: Literal["anomaly", "prediction", "efficiency"]
    probability: Decimal | None
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    suggested_action: str | None
    details: dict[str, Any]
    is_resolved: bool
    created_at: datetime


class MlAnalyzeResponse(BaseModel):
    analyzed_assets: int
    anomaly_insights: int
    prediction_insights: int

