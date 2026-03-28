# pack_catalog_sync Developer Guide

## Purpose

`pack_catalog_sync` is the developer-facing maintenance tool for keeping Semantic Prompt pack JSON files and the `category_meta.sqlite` catalog aligned.

It currently supports four workflows:

- `audit` — inspect canonical packs and DB state without writing changes
- `intake` — install new pack submissions from a staging folder into the canonical packs tree
- `sync-json-to-db` — treat the canonical packs tree as source of truth and sync it into the DB
- `sync-db-to-json` — rebuild canonical JSON files from DB records

The package is split by responsibility so planning, validation, conflict handling, applying, and CLI wiring can evolve independently.

---

## High-level architecture

### Core flow

For most commands, execution follows this sequence:

1. Parse CLI arguments in `cli.py`
2. Build a plan in `service.py`
3. Resolve conflicts, optionally isolating conflicted files
4. Apply the plan with the appropriate writer
5. Print a human summary and optionally emit a JSON report

### Modules

- `cli.py` — argument parsing and command entrypoint
- `service.py` — orchestration layer that routes commands to planners and apply functions
- `planner.py` — planning for canonical pack workflows (`audit`, `sync-json-to-db`, `sync-db-to-json`)
- `intake.py` — intake scan, intake planning, and intake install logic
- `validation.py` — hard validation plus advisory warnings
- `apply.py` — canonical pack write paths and DB-to-JSON rebuild logic
- `db.py` — schema setup and DB load/upsert helpers
- `helpers.py` — category normalization, metadata shaping, JSON IO, backups, path cleanup
- `scanner.py` — canonical pack scanning and schema field discovery
- `conflicts.py` — conflict review folder creation and conflict filtering
- `models.py` — dataclasses such as `PackState`, `PlannedAction`, `ConflictRecord`, and `SyncPlan`
- `reporting.py` — console plan printing and report writing

---

## Command behavior

## `audit`

`audit` scans canonical packs under `--packs-root`, compares them to DB state, validates pack structure, computes a plan, and prints/report-only results. It never writes changes.

Use it when:

- checking for category drift
- checking missing metadata auto-fills
- checking collisions before a real sync
- reviewing `db_only_record` items before rebuilding JSON from DB

## `sync-json-to-db`

This mode treats the canonical packs folder as the source of truth. It:

- scans canonical pack JSON files
- decides the effective category for each file
- normalizes `_meta`
- writes repaired/moved canonical JSON if needed
- upserts matching DB rows

This is the normal mode for **directly editing packs in the canonical `packs/` tree**.

## `sync-db-to-json`

This mode treats the DB as source of truth and rebuilds canonical JSON files. It:

- uses DB category and metadata as authoritative
- merges entry content from any matching source files by `cat_id`
- writes canonical JSON into the category-derived destination path
- can optionally remove old non-canonical source files

Use it when you need to repair filesystem layout from DB records.

## `intake`

This mode scans an intake/staging folder and installs valid submissions into canonical packs. It:

- scans JSON files from `--intake-root`
- resolves category from `_meta.category` or path fallback
- auto-generates `cat_id` if missing
- normalizes `_meta`
- writes the accepted file into canonical `packs/<category>/<cat_id>.json`
- inserts a DB row
- optionally deletes processed intake files

Intake also supports policy-based handling for categories that already exist in the DB through `--intake-policy`.

This makes intake usable for both:

- brand-new category installs
- staged additions under existing category families, when policy allows them

### Intake category policy

`intake` now supports policy-based handling for categories that already exist in the DB.

The `--intake-policy` option controls behavior:

- `new-only`
  - existing category in DB becomes a conflict
- `require-review`
  - existing category in DB becomes a review/conflict item and is not auto-applied
- `allow-existing`
  - existing category in DB is allowed
  - the intake file is installed as a new pack under that category using its own unique `cat_id`
  - the action resolution is reported as `intake_extend_category`
  - it does not reuse the existing DB row
  - it does not overwrite the existing cat_id
  - it installs a new file under the same category using a unique cat_id

In all intake modes, an already-existing `cat_id` in the DB remains a hard conflict.

## Data model

## `PackState`

Represents one scanned JSON file.

Important fields:

- `path` — absolute file path
- `rel_path` — path relative to scan root
- `data` — full JSON object
- `meta` — `_meta` object if present
- `entry_keys` — top-level entry keys excluding `_meta`
- `cat_id` — effective ID, generated if missing
- `file_category` — normalized `_meta.category`
- `path_category` — category inferred from folder path / filename
- `db_category` — category already associated with this `cat_id` in DB, if any
- `exists_in_db` — whether the file already maps to a DB row
- `is_new_to_db` — whether it should be treated as new

## `PlannedAction`

Represents one proposed write or keep action.

Important fields:

- `source_rel_path`
- `category`
- `cat_id`
- `dest_rel_path`
- `resolution`
- `db_action` (`insert`, `update`, `keep`)
- `json_action` (`write`, `update`, `skip` depending on planner/apply path)
- `move_required`
- `missing_fields_added`
- `warnings`

## `ConflictRecord`

Structured conflict entry with:

- human message
- source files involved
- category and `cat_id`
- an `extra` dict for conflict code and any debugging metadata

## `SyncPlan`

A plan contains:

- action list
- conflict strings
- structured conflict records
- conflicted relative paths
- warnings
- summary/report helpers

---

## Validation model

Validation is intentionally split into two layers:

### Hard validation

These should block the file from being applied:

- root JSON is not an object
- missing `_meta`
- invalid `_meta` shape
- missing required `_meta.category`, `_meta.title`, or `_meta.notes`
- illegal `keys` container instead of top-level entries
- entry value is not an object

### Advisory validation

These do not block sync but are surfaced as warnings because they make search/discovery weaker:

- missing `meta.search_tags`
- missing `meta.aliases`
- missing `meta.related_categories`
- entries without `tags`

This keeps the tool permissive for authors while still nudging packs toward better search quality.

---

## Canonical category resolution

For canonical pack workflows, `planner.py` decides the effective category with this rough precedence:

1. If file is new to DB and has `_meta.category`, use it
2. If file is new and `_meta.category` is missing, fall back to path-derived category
3. If DB is trusted (`--trust-db`), DB category wins when present
4. Otherwise file category wins, with warnings/conflicts if it disagrees with DB
5. If file category is missing but DB category exists, repair from DB
6. If both are missing, fall back to path-derived category
7. If none can be resolved, the file becomes a conflict

Result strings such as `db_wins`, `file_wins`, `path_fallback`, `db_repairs_missing_file_category`, and `db_only_record` make reporting easier.

---

## Metadata shaping

`helpers.ensure_meta_shape()` is one of the key pieces of the tool. It takes whatever `_meta` exists and returns a shaped version consistent with the known schema.

It currently fills or normalizes fields such as:

- `title`
- `notes`
- `generator_family`
- `generator_slot`
- `generatable`
- `schema_version`
- list-like fields such as `parents`, `children`, `related_categories`, `aliases`, `search_tags`, and `pack_paths`

It also forces `pack_paths` to match the file destination path.

This means contributors only need the required authoring fields; generated fields are tool-managed.

---

## Conflict handling

Conflicts are not just printed and forgotten.

When conflicts exist and the run is not aborted:

1. `service.resolve_conflicts_for_apply()` calls `conflicts.isolate_conflicted_files()`
2. conflicted files are copied into a review folder under a timestamped conflict directory
3. `filter_conflicted_actions()` removes actions touching conflicted files
4. non-conflicted actions may still apply as a partial run

If every action is conflicted, the run returns a `conflicts_only` status and nothing is written.

Good conflict examples:

- category collision
- `cat_id` collision
- invalid pack structure
- unresolved category
- intake category already exists in DB

---

## CLI reference

## Common arguments

Used by all commands:

- `--packs-root` — canonical packs root
- `--db` — path to `category_meta.sqlite`
- `--report-json` — optional JSON report output path
- `--strict-category-conflicts` — escalate category disagreements into conflicts
- `--trust-db` — let DB category win when file and DB disagree
- `--limit` — max actions shown in console preview

## Write-mode arguments

Used by non-`audit` commands:

- `--apply` — actually write changes; without this the run is preview-only
- `--backup` — create backups before writes
- `--abort-on-conflicts` — stop instead of isolating conflicted files and partially applying

## Intake-only arguments
- `--intake-policy` — controls how intake handles categories that already exist in the DB:
  - `new-only`
  - `allow-existing`
  - `require-review`
- `--intake-root` — staging folder containing new submission JSON files
- `--keep-intake-files` — do not remove successfully installed intake files

## `sync-db-to-json` only

- `--no-cleanup-old` — keep old source files rather than deleting non-canonical duplicates after rebuild

---

## Example commands

### Audit canonical packs

```bat
python -m pack_catalog_sync audit ^
  --packs-root "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\packs" ^
  --db "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\data\category_meta.sqlite"
```

### Sync canonical packs into DB

```bat
python -m pack_catalog_sync sync-json-to-db ^
  --packs-root "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\packs" ^
  --db "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\data\category_meta.sqlite" ^
  --apply ^
  --backup
```

### Install new intake submissions

```bat
python -m pack_catalog_sync intake ^
  --packs-root "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\packs" ^
  --intake-root "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\intake" ^
  --db "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\data\category_meta.sqlite" ^
  --apply ^
  --backup
```

### Rebuild canonical JSON from DB

```bat
python -m pack_catalog_sync sync-db-to-json ^
  --packs-root "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\packs" ^
  --db "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\data\category_meta.sqlite" ^
  --apply ^
  --backup
```

### Install intake submissions, but require review for existing categories

```bat
python -m pack_catalog_sync intake ^
  --packs-root "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\packs" ^
  --intake-root "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\intake" ^
  --db "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\data\category_meta.sqlite" ^
  --intake-policy require-review ^
  --apply ^
  --backup
```

### Install intake submissions and allow extensions under existing categories

```
python -m pack_catalog_sync intake ^
  --packs-root "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\packs" ^
  --intake-root "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\intake" ^
  --db "C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\data\category_meta.sqlite" ^
  --intake-policy allow-existing ^
  --apply ^
  --backup
```


---

## Pack authoring assumptions

The sync tool assumes packs follow the pack schema and taxonomy conventions used elsewhere in the project.

### Minimal pack structure

A valid pack should look like this:

```json
{
  "_meta": {
    "category": "appearance.eye_color",
    "title": "Eye Colors",
    "notes": "Common eye colors used in character descriptions."
  },
  "blue eyes": {},
  "green eyes": {}
}
```

### Required `_meta`

- `category`
- `title`
- `notes`

### Generated fields authors should not add manually

- `cat_id`
- `generator_family`
- `generator_slot`
- `generatable`
- `pack_paths`
- `schema_version`

### Entry shape

- entries live at the top level
- each entry should be an object
- common entry fields are `tags`, `aliases`, `related`, `requires`, and `excludes`

### Taxonomy expectations

- categories are dot-separated
- lowercase only
- one logical concept group per pack
- `.mod` is used for modifier/component branches like `clothing.garments.bottoms.pants.mod.length`

---

## Backups, reports, and side effects

### Backups

When `--backup` is used, the tool writes timestamped backup copies under a `backups/pack_catalog_sync` folder adjacent to the canonical packs tree.

### Reports

If `--report-json` is provided, the tool writes a machine-readable JSON result that includes:

- plan summary
- conflict list
- structured conflict records
- actions
- any partial apply / conflict review metadata

Conflicts are structured and include typed codes such as:

- intake_existing_category

- intake_existing_category_review

- intake_existing_cat_id

- intake_duplicate_category

- intake_duplicate_cat_id

### Conflict review folders

Conflicted files are copied into a timestamped conflict review folder under a `conflicts/pack_catalog_sync` root near the packs tree.

---

## Known current gaps

These are worth knowing as a developer working on the next revision.

1. Intake policy now exists, but intake still treats an already-existing `cat_id` in the DB as a hard conflict in all modes.
2. `allow-existing` permits extending an existing category, but intake still installs a new canonical file with a new `cat_id`; it does not merge into an existing DB row.
3. `pack_bundle_manager` output can be consumed by intake only when it already emits valid pack JSON following the same schema expectations.
4. `planner.py` still carries a fair amount of validation/conflict logic that could eventually move into more structured planner/service layers.
5. Reporting could still improve with more explicit changed-field previews and richer action-level detail.

---

## Suggested next engineering steps

If you continue improving the tool, these are the highest-value next steps:

1. Add tests for `--intake-policy` behavior:
   - `new-only`
   - `require-review`
   - `allow-existing`
2. Improve report ergonomics with clearer changed-field previews and more explicit action summaries
3. Add more tests around category resolution, `ensure_meta_shape()`, and intake conflict scenarios
4. Consider whether intake should eventually support a separate “merge into existing canonical record” workflow, distinct from “install as a new file under an existing category”
5. Share more helpers with `sync_packs_from_db.py` to reduce duplicate logic

---

## Quick mental model

Use this rule of thumb:

- **Edit canonical packs directly** -> `sync-json-to-db`
- **Import staged submissions as new installs** -> `intake --intake-policy new-only`
- **Import staged submissions but review category overlap** -> `intake --intake-policy require-review`
- **Import staged submissions that may extend existing categories** -> `intake --intake-policy allow-existing`
- **Inspect everything first** -> `audit`
- **Repair filesystem layout from DB** -> `sync-db-to-json`

That keeps the maintenance workflow predictable and avoids mixing install/staging behavior with canonical editing behavior.
