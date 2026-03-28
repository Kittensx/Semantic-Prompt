import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS bundles (
    bundle_id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    version TEXT,
    bundle_hash TEXT,
    min_app_version TEXT,
    schema_version TEXT,
    author TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS bundle_releases (
    bundle_id TEXT,
    version TEXT,
    created_at TEXT,
    notes TEXT,
    PRIMARY KEY (bundle_id, version)
);

CREATE TABLE IF NOT EXISTS pack_payloads (
    cat_id TEXT PRIMARY KEY,
    category TEXT,
    pack_json TEXT,
    content_hash TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS bundle_packs (
    bundle_id TEXT,
    cat_id TEXT,
    sort_order INTEGER,
    PRIMARY KEY (bundle_id, cat_id)
);

CREATE TABLE IF NOT EXISTS pack_dependencies (
    cat_id TEXT,
    depends_on_cat_id TEXT,
    dependency_type TEXT,
    PRIMARY KEY (cat_id, depends_on_cat_id, dependency_type)
);
"""


class BundleDB:
    def __init__(self, db_path):
        self.db_path = Path(db_path)

    def connect(self):
        return sqlite3.connect(self.db_path)

    def initialize(self):
        with self.connect() as con:
            con.executescript(SCHEMA)

    def list_bundles(self):
        with self.connect() as con:
            cur = con.execute(
                "SELECT bundle_id, version FROM bundles ORDER BY bundle_id"
            )
            return cur.fetchall()

    def insert_bundle(
        self,
        bundle_id,
        name=None,
        description=None,
        version="1.0.0",
        bundle_hash=None,
        min_app_version=None,
        schema_version="1",
        author=None,
    ):
        with self.connect() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO bundles
                (bundle_id, name, description, version, bundle_hash,
                 min_app_version, schema_version, author)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle_id,
                    name,
                    description,
                    version,
                    bundle_hash,
                    min_app_version,
                    schema_version,
                    author,
                ),
            )

    def update_bundle_hash(self, bundle_id, bundle_hash):
        with self.connect() as con:
            con.execute(
                "UPDATE bundles SET bundle_hash = ? WHERE bundle_id = ?",
                (bundle_hash, bundle_id),
            )

    def get_bundle_info(self, bundle_id):
        with self.connect() as con:
            cur = con.execute(
                """
                SELECT bundle_id, name, description, version, bundle_hash,
                       min_app_version, schema_version, author
                FROM bundles
                WHERE bundle_id = ?
                """,
                (bundle_id,),
            )
            return cur.fetchone()

    def insert_pack(self, cat_id, category, pack_json, content_hash):
        with self.connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO pack_payloads
                (cat_id, category, pack_json, content_hash)
                VALUES (?, ?, ?, ?)
                """,
                (cat_id, category, pack_json, content_hash),
            )

    def add_pack_to_bundle(self, bundle_id, cat_id, sort_order=0):
        with self.connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO bundle_packs(bundle_id, cat_id, sort_order)
                VALUES (?, ?, ?)
                """,
                (bundle_id, cat_id, sort_order),
            )

    def get_bundle_packs(self, bundle_id):
        with self.connect() as con:
            cur = con.execute(
                """
                SELECT p.cat_id, p.category, p.pack_json
                FROM pack_payloads p
                JOIN bundle_packs b ON p.cat_id = b.cat_id
                WHERE b.bundle_id = ?
                ORDER BY b.sort_order, p.cat_id
                """,
                (bundle_id,),
            )
            return cur.fetchall()

    def add_dependency(self, cat_id, depends_on_cat_id, dependency_type="requires"):
        with self.connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO pack_dependencies
                (cat_id, depends_on_cat_id, dependency_type)
                VALUES (?, ?, ?)
                """,
                (cat_id, depends_on_cat_id, dependency_type),
            )

    def get_dependencies(self, cat_id):
        with self.connect() as con:
            cur = con.execute(
                """
                SELECT depends_on_cat_id, dependency_type
                FROM pack_dependencies
                WHERE cat_id = ?
                ORDER BY dependency_type, depends_on_cat_id
                """,
                (cat_id,),
            )
            return cur.fetchall()

    def get_bundle_cat_ids(self, bundle_id):
        with self.connect() as con:
            cur = con.execute(
                "SELECT cat_id FROM bundle_packs WHERE bundle_id = ?",
                (bundle_id,),
            )
            return {row[0] for row in cur.fetchall()}