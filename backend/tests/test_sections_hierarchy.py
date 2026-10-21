import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.models.organization import Section
from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.localization import SectionTranslation
from app.models.tmc import TmcDocument
from app.models.work_orders import WorkOrder
from app.models.work_records import MaintenanceLog
from app.models.organization import Employee
from app.schemas.references import SectionCreate, SectionUpdate
from app.services import references
from app.services.references import _validate_section_hierarchy


class SectionHierarchyTests(unittest.IsolatedAsyncioTestCase):
    async def test_self_parent_is_rejected(self):
        db = AsyncMock()
        section_id = uuid4()

        with self.assertRaises(HTTPException) as raised:
            await _validate_section_hierarchy(
                db,
                section_id=section_id,
                parent_id=section_id,
                unit_type="section",
            )

        self.assertEqual(raised.exception.status_code, 409)

    async def test_move_under_descendant_is_rejected(self):
        db = AsyncMock()
        parent_id = uuid4()
        child_id = uuid4()

        root = Section(id=parent_id, name="Root", unit_type="section", parent_id=None)
        child = Section(
            id=child_id, name="Child", unit_type="section", parent_id=parent_id
        )

        async def get_record(_db, _model, record_id):
            return {parent_id: root, child_id: child}.get(record_id)

        with patch(
            "app.services.references.repository.get_record",
            new=AsyncMock(side_effect=get_record),
        ), patch(
            "app.services.references.repository.list_all_sections",
            new=AsyncMock(return_value=[root, child]),
        ):
            with self.assertRaises(HTTPException) as raised:
                await _validate_section_hierarchy(
                    db,
                    section_id=parent_id,
                    parent_id=child_id,
                    unit_type="section",
                )

        self.assertEqual(raised.exception.status_code, 409)

    async def test_existing_cycle_in_parent_chain_is_rejected(self):
        db = AsyncMock()
        first_id = uuid4()
        second_id = uuid4()
        first = Section(id=first_id, name="First", unit_type="section", parent_id=second_id)
        second = Section(id=second_id, name="Second", unit_type="section", parent_id=first_id)

        with patch(
            "app.services.references.repository.get_record",
            new=AsyncMock(
                side_effect=lambda _db, _model, record_id: {
                    first_id: first,
                    second_id: second,
                }.get(record_id)
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await _validate_section_hierarchy(
                    db,
                    section_id=uuid4(),
                    parent_id=first_id,
                    unit_type="section",
                )

        self.assertEqual(raised.exception.status_code, 409)

    async def test_invalid_typed_parent_is_rejected(self):
        db = AsyncMock()
        parent_id = uuid4()
        parent = Section(id=parent_id, name="Section", unit_type="section")

        with patch(
            "app.services.references.repository.get_record",
            new=AsyncMock(return_value=parent),
        ):
            with self.assertRaises(HTTPException) as raised:
                await _validate_section_hierarchy(
                    db,
                    section_id=None,
                    parent_id=parent_id,
                    unit_type="division",
                )

        self.assertEqual(raised.exception.status_code, 409)

    async def test_type_change_cannot_invalidate_child(self):
        db = AsyncMock()
        section_id = uuid4()
        child = Section(
            id=uuid4(),
            name="Child",
            unit_type="division",
            parent_id=section_id,
        )

        with patch(
            "app.services.references.repository.list_all_sections",
            new=AsyncMock(return_value=[child]),
        ):
            with self.assertRaises(HTTPException) as raised:
                await _validate_section_hierarchy(
                    db,
                    section_id=section_id,
                    parent_id=None,
                    unit_type="section",
                )

        self.assertEqual(raised.exception.status_code, 409)

    async def test_tree_contains_nested_descendants_and_localized_names(self):
        db = AsyncMock()
        root_id, child_id, leaf_id = uuid4(), uuid4(), uuid4()
        rows = [
            Section(id=root_id, name="Root", unit_type="department"),
            Section(
                id=child_id,
                name="Child",
                unit_type="division",
                parent_id=root_id,
            ),
            Section(
                id=leaf_id,
                name="Leaf",
                unit_type="section",
                parent_id=child_id,
            ),
        ]
        translations = {
            root_id: {"ru": "Root", "uz-Latn": "Ildiz", "uz-Cyrl": "Илдиз"}
        }

        with patch(
            "app.services.references.repository.list_all_sections",
            new=AsyncMock(return_value=rows),
        ), patch(
            "app.services.references.repository.get_section_translations",
            new=AsyncMock(return_value=translations),
        ):
            result = await references.list_section_tree(db, q="Ildiz")

        self.assertEqual(result[0]["id"], root_id)
        self.assertEqual(result[0]["children"][0]["id"], child_id)
        self.assertEqual(
            result[0]["children"][0]["children"][0]["id"], leaf_id
        )
        self.assertEqual(result[0]["translations"]["uz-Latn"], "Ildiz")

    async def test_archive_preserves_section_instead_of_deleting_it(self):
        db = AsyncMock()
        section = Section(id=uuid4(), name="Historical unit", unit_type="section")

        with patch(
            "app.services.references.get_section",
            new=AsyncMock(return_value=section),
        ), patch(
            "app.services.references.repository.has_active_children",
            new=AsyncMock(return_value=False),
        ):
            await references.delete_section(db, section.id)

        self.assertTrue(section.is_archived)
        db.delete.assert_not_awaited()
        db.commit.assert_awaited_once()

    async def test_update_persists_all_translations(self):
        db = AsyncMock()
        db.add_all = MagicMock()
        section = Section(id=uuid4(), name="Old", unit_type="section")
        translations = {
            "ru": "Новое",
            "uz-Latn": "Yangi",
            "uz-Cyrl": "Янги",
        }

        with patch(
            "app.services.references.get_section",
            new=AsyncMock(return_value=section),
        ), patch(
            "app.services.references._validate_section_hierarchy",
            new=AsyncMock(),
        ), patch(
            "app.services.references._commit_or_conflict",
            new=AsyncMock(),
        ):
            result = await references.update_section(
                db,
                section.id,
                SectionUpdate(translations=translations),
            )

        self.assertIs(result, section)
        self.assertEqual(section.name, "Новое")
        self.assertEqual(section.translations, translations)
        db.add_all.assert_called_once()
        rows = db.add_all.call_args.args[0]
        self.assertEqual(
            {(row.locale, row.name) for row in rows},
            set(translations.items()),
        )

    def test_historical_foreign_keys_still_target_sections(self):
        linked_models = (
            User,
            Employee,
            FixedAsset,
            WorkOrder,
            MaintenanceLog,
            TmcDocument,
        )
        for model in linked_models:
            with self.subTest(model=model.__tablename__):
                foreign_keys = model.__table__.c.section_id.foreign_keys
                self.assertTrue(foreign_keys)
                self.assertTrue(
                    any(
                        key.target_fullname == "sections.id"
                        for key in foreign_keys
                    )
                )

    def test_department_table_remains_separate(self):
        self.assertIsNot(Section.__table__, Employee.__table__)
        department_fk = Section.__table__.c.department_id.foreign_keys
        self.assertTrue(
            any(key.target_fullname == "departments.id" for key in department_fk)
        )

    def test_create_requires_all_translations_when_provided(self):
        with self.assertRaises(ValueError):
            SectionCreate(
                name="Unit",
                translations={"ru": "Unit"},
            )

    def test_translation_names_are_normalized_and_update_can_move(self):
        payload = SectionUpdate(
            parent_id=None,
            translations={
                "ru": " Русское название ",
                "uz-Latn": " O‘zbekcha ",
                "uz-Cyrl": " Ўзбекча ",
            },
        )

        self.assertIsNone(payload.parent_id)
        self.assertEqual(payload.translations["ru"], "Русское название")


if __name__ == "__main__":
    unittest.main()
