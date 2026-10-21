import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.models.organization import Section
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

    async def test_cycle_is_rejected(self):
        db = AsyncMock()
        parent_id = uuid4()
        child_id = uuid4()

        root = Section(id=parent_id, name="Root", unit_type="section", parent_id=child_id)
        child = Section(id=child_id, name="Child", unit_type="section", parent_id=parent_id)

        with patch("app.services.references.repository.get_record", new=AsyncMock(side_effect=lambda _db, model, record_id: {parent_id: root, child_id: child}.get(record_id))):
            with self.assertRaises(HTTPException) as raised:
                await _validate_section_hierarchy(
                    db,
                    section_id=parent_id,
                    parent_id=child_id,
                    unit_type="section",
                )

        self.assertEqual(raised.exception.status_code, 409)

    async def test_division_requires_department_or_division_parent(self):
        db = AsyncMock()
        division_id = uuid4()
        section_id = uuid4()
        parent = Section(id=section_id, name="Section", unit_type="section")

        with patch("app.services.references.repository.get_record", new=AsyncMock(side_effect=lambda _db, model, record_id: parent if record_id == section_id else None)):
            with self.assertRaises(HTTPException) as raised:
                await _validate_section_hierarchy(
                    db,
                    section_id=division_id,
                    parent_id=section_id,
                    unit_type="division",
                )

        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
