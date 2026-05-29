from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.template_store import TemplateStore


class TemplateStoreTests(unittest.TestCase):
    def test_save_and_list_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "templates.json"
            store = TemplateStore(path)
            idx = store.save_template(
                "Test Name",
                "email",
                "Hello {{patient_name}} with member {member_id}",
                visibility="shared",
            )
            self.assertEqual(idx, 0)
            items = store.list_templates()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["name"], "Test Name")
            self.assertEqual(items[0]["placeholders"], ["member_id", "patient_name"])

    def test_delete_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "templates.json"
            store = TemplateStore(path)
            store.save_template("A", "email", "Body", visibility="shared")
            items = store.list_templates()
            store.delete_template(int(items[0]["index"]))
            self.assertEqual(store.list_templates(), [])

    def test_legacy_templates_without_visibility_are_not_shared_to_staff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "templates.json"
            path.write_text(
                '[{"name":"Legacy","type":"email","content":"Body","created_at":"2026-01-01T00:00:00Z"}]',
                encoding="utf-8",
            )
            store = TemplateStore(path)

            self.assertEqual(store.list_templates(user_id="staff-1", role="staff"), [])
            admin_items = store.list_templates(user_id="admin-1", role="admin")
            self.assertEqual(len(admin_items), 1)
            self.assertEqual(admin_items[0]["visibility"], "personal")

    def test_tags_are_normalized_for_save_and_legacy_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "templates.json"
            store = TemplateStore(path)
            idx = store.save_template(
                "Tagged",
                "email",
                "Body",
                visibility="shared",
                tags=["Appeal", "urgent", "urgent", " "],
            )
            self.assertEqual(idx, 0)
            items = store.list_templates()
            self.assertEqual(items[0]["tags"], ["appeal", "urgent"])

            path.write_text(
                (
                    '[{"name":"Legacy Tag","type":"email","content":"Body","created_at":"2026-01-01T00:00:00Z",'
                    '"visibility":"shared","tags":"wrong-shape"}]'
                ),
                encoding="utf-8",
            )
            legacy_items = store.list_templates()
            self.assertEqual(legacy_items[0]["tags"], [])


if __name__ == "__main__":
    unittest.main()
