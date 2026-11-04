from app.core.config import settings
from app.integrations.base import SourceObject
from app.integrations.gtk_client import GtkClient


class GtkSourceAdapter:
    source = "gtk"
    mirror_table = "gtk_locomotives,gtk_carriages"

    def __init__(self, client: GtkClient | None = None) -> None:
        self.client = client or GtkClient(
            settings.gtk_host,
            settings.gtk_user,
            settings.gtk_password,
            settings.gtk_page_path,
            settings.gtk_page_query,
        )

    async def fetch_gtk_snapshot(self) -> dict:
        return await self.client.fetch_snapshot()

    async def fetch_snapshot(self) -> list[SourceObject]:
        snapshot = await self.fetch_gtk_snapshot()
        objects = [
            SourceObject(
                source=self.source,
                external_id=str(row["gtk_id"]),
                name=row.get("name"),
                number=row.get("garage_number"),
                inventory=row.get("inventory_number"),
                model=row.get("model_name"),
                type="locomotive",
            )
            for row in snapshot["locomotives"]
        ]
        objects.extend(
            SourceObject(
                source=self.source,
                external_id=str(row["gtk_id"]),
                name=row.get("name"),
                number=row.get("reg_number"),
                inventory=row.get("inventory_number"),
                model=row.get("model_name"),
                type="carriage",
            )
            for row in snapshot["carriages"]
        )
        return objects
