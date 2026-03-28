import json
import sqlite3
from pathlib import Path


class CategoryMetaDB:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._cat_cache = {}

    def get_by_cat_id(self, cat_id: str):
        cat_id = str(cat_id).strip()
        if not cat_id:
            raise ValueError("Empty cat_id")

        if cat_id in self._cat_cache:
            return self._cat_cache[cat_id]

        row = self.conn.execute(
            """
            SELECT cat_id, category, meta_json
            FROM category_meta
            WHERE cat_id = ?
            """,
            (cat_id,),
        ).fetchone()

        if row is None:
            raise KeyError(f"Unknown cat_id: {cat_id}")

        meta = {}
        if row["meta_json"]:
            try:
                meta = json.loads(row["meta_json"])
            except Exception:
                meta = {}

        if not isinstance(meta, dict):
            meta = {}

        meta["cat_id"] = row["cat_id"]
        meta["category"] = row["category"]

        self._cat_cache[cat_id] = meta
        return meta

    def get_category(self, cat_id: str) -> str:
        return str(self.get_by_cat_id(cat_id)["category"])