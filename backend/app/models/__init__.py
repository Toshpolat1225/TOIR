from app.models.assets import FixedAsset, MileageHistory, WialonSettings
from app.models.asset_models import AssetModel
from app.models.analytics import DailyReadinessSnapshot
from app.models.asset_source_links import AssetSourceLink
from app.models.asset_field_changes import AssetFieldChange
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.identity import LoginAttempt, RefreshToken, User
from app.models.gtk import (
    GtkCarriage,
    GtkLocomotive,
    GtkSyncRun,
    GtkTrain,
    GtkTrainMember,
)
from app.models.inventory import Nomenclature, NomenclatureNorm, WorkTypeTemplate
from app.models.localization import (
    DepartmentTranslation,
    FixedAssetStatus,
    FixedAssetStatusTranslation,
    FixedAssetType,
    FixedAssetTypeTranslation,
    NomenclatureTranslation,
    SectionTranslation,
    WorkSubtaskTranslation,
    WorkTypeTranslation,
)
from app.models.maintenance import (
    MaintenanceInterval,
    MaintenancePlan,
    MaintenanceSettings,
    WorkSubtask,
    WorkType,
)
from app.models.organization import Department, Employee, Section
from app.models.permissions import Permission, PermissionAudit, RolePermission
from app.models.tmc import TmcDocument, TmcDocumentItem
from app.models.wialon_counters import WialonCounterState, WialonRejectedReading
from app.models.wialon_units import WialonUnitRecord
from app.models.work_orders import WorkOrder, WorkOrderItem, WorkOrderRepair
from app.models.work_records import AiInsight, MaintenanceLog

__all__ = [
    "AiInsight",
    "AssetSourceLink",
    "AssetFieldChange",
    "AuditLog",
    "AssetModel",
    "Base",
    "Department",
    "DepartmentTranslation",
    "DailyReadinessSnapshot",
    "Employee",
    "FixedAsset",
    "GtkCarriage",
    "GtkLocomotive",
    "GtkSyncRun",
    "GtkTrain",
    "GtkTrainMember",
    "FixedAssetStatus",
    "FixedAssetStatusTranslation",
    "FixedAssetType",
    "FixedAssetTypeTranslation",
    "LoginAttempt",
    "MaintenanceInterval",
    "MaintenanceLog",
    "MaintenancePlan",
    "MaintenanceSettings",
    "MileageHistory",
    "Nomenclature",
    "NomenclatureTranslation",
    "NomenclatureNorm",
    "Permission",
    "PermissionAudit",
    "RefreshToken",
    "RolePermission",
    "Section",
    "SectionTranslation",
    "TmcDocument",
    "TmcDocumentItem",
    "User",
    "WialonSettings",
    "WialonCounterState",
    "WialonRejectedReading",
    "WialonUnitRecord",
    "WorkOrder",
    "WorkOrderItem",
    "WorkOrderRepair",
    "WorkSubtask",
    "WorkSubtaskTranslation",
    "WorkType",
    "WorkTypeTranslation",
    "WorkTypeTemplate",
]
