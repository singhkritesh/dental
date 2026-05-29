from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.errors import AppError
from services.field_dictionary_store import FieldDictionaryStore


class FieldDictionaryStoreTests(unittest.TestCase):
    def test_defaults_exist_when_store_is_new(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FieldDictionaryStore(Path(tmp) / "field_dictionary.json")
            entries = store.list_entries()
            self.assertTrue(any(item["key"] == "patient_name" for item in entries))

    def test_upsert_normalizes_key_and_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FieldDictionaryStore(Path(tmp) / "field_dictionary.json")
            saved = store.upsert_entry(
                " Patient Number ",
                label="Patient Number",
                aliases=[" Chart Number ", "chart number", "ID#"],
            )
            self.assertEqual(saved["key"], "patient_number")
            self.assertEqual(saved["aliases"], ["chart number", "id"])

    def test_delete_missing_field_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FieldDictionaryStore(Path(tmp) / "field_dictionary.json")
            with self.assertRaises(AppError):
                store.delete_entry("unknown_field")


if __name__ == "__main__":
    unittest.main()
