from app.models.assets import FixedAsset, MileageHistory, WialonSettings
from app.models.analytics import DailyReadinessSnapshot
from app.models.base import Base
from app.models.identity import RefreshToken, User
from app.models.inventory import Nomenclature, NomenclatureNorm, WorkTypeTemplate
from app.models.maintenance import (
    MaintenanceInterval,
    MaintenancePlan,
    MaintenanceSettings,
    WorkSubtask,
    WorkType,
)
from app.models.organization import Department, Employee, Section
from app.models.tmc import TmcDocument, TmcDocumentItem
from app.models.work_orders import WorkOrder, WorkOrderItem, WorkOrderRepair
from app.models.work_records import AiInsight, MaintenanceLog

__all__ = [
    "AiInsight",
    "Base",
    "Department",
    "DailyReadinessSnapshot",
    "Employee",
    "FixedAsset",
    "MaintenanceInterval",
    "MaintenanceLog",
    "MaintenancePlan",
    "MaintenanceSettings",
    "MileageHistory",
    "Nomenclature",
    "NomenclatureNorm",
    "RefreshToken",
    "Section",
    "TmcDocument",
    "TmcDocumentItem",
    "User",
    "WialonSettings",
    "WorkOrder",
    "WorkOrderItem",
    "WorkOrderRepair",
    "WorkSubtask",
    "WorkType",
    "WorkTypeTemplate",
]
