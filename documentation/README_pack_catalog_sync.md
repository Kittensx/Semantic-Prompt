# Pack Catalog Sync Dev Tool

A standalone developer utility for managing semantic prompt pack files and `category_meta.sqlite`.

It supports four workflows:

- `audit`: preview what would happen without writing anything
- `intake`: scan pack files, normalize metadata, assign/adopt `cat_id`, move files into canonical category folders, and upsert the DB
- `sync-json-to-db`: treat JSON files as authoritative and push metadata changes into SQLite
- `sync-db-to-json`: treat the database as authoritative and push metadata changes back into JSON files

This tool is intentionally explicit and deterministic. It does **not** perform silent background sync.

## Core design

- `cat_id` is the stable machine identity
- `category` is the human-readable canonical taxonomy
- folder path is derived from `category`
- filename is `<cat_id>.json`
- `_meta.category` stays in JSON and remains human-meaningful
- DB stores both `cat_id` and `category`

## Minimal user-authored metadata

For new or user-created packs, the minimum recommended `_meta` is:

```json
{
  "_meta": {
    "category": "clothing.garments.bottoms.pants",
    "title": "Pants Styles",
    "notes": "Styles of pants such as jeans, cargo pants, leggings, and slacks."
  }
}
```

The tool will auto-add missing helper fields like:

- `cat_id`
- `generator_family`
- `generator_slot`
- `generatable`
- `parents`
- `children`
- `related_categories`
- `aliases`
- `search_tags`
- `pack_paths`
- `schema_version`

## Default conflict policy

### Category conflicts

If `_meta.category` conflicts with the DB category:

- new file not in DB: trust the file
- existing file already in DB: trust the file by default
- use `--trust-db` to make the DB win instead
- use `--strict-category-conflicts` to stop apply mode when category conflicts are present

### Why this policy exists

If a file already exists in the DB and its JSON category changed, that usually means the JSON was edited manually and should not be silently overwritten.

## Canonical disk layout

The canonical location for a pack file is:

```text
<packs_root>/<category parts>/<cat_id>.json
```

Example:

```text
semantic/packs/clothing/garments/bottoms/pants/cat_ab12cd34ef56.json
```

for category:

```text
clothing.garments.bottoms.pants
```

## Commands

## 1) Audit

Preview everything without writing anything.

```bash
python pack_catalog_sync.py audit \
  --packs-root "C:/Programs/A1111/stable-diffusion-webui/extensions/semantic_prompt/semantic/packs" \
  --db "C:/Programs/A1111/stable-diffusion-webui/extensions/semantic_prompt/category_meta.sqlite"
```

Helpful flags:

- `--report-json report.json`
- `--limit 200`
- `--trust-db`
- `--strict-category-conflicts`

## 2) Intake

Use this when you scanned or dropped in new pack files and want to:

- assign/adopt `cat_id`
- normalize metadata
- move files into canonical category folders
- insert/update the DB

Preview first:

```bash
python pack_catalog_sync.py intake \
  --packs-root "C:/.../semantic/packs" \
  --db "C:/.../category_meta.sqlite"
```

Apply:

```bash
python pack_catalog_sync.py intake \
  --packs-root "C:/.../semantic/packs" \
  --db "C:/.../category_meta.sqlite" \
  --apply --backup
```

## 3) Sync JSON -> DB

Use this after manually editing `_meta` inside JSON files.

Preview:

```bash
python pack_catalog_sync.py sync-json-to-db \
  --packs-root "C:/.../semantic/packs" \
  --db "C:/.../category_meta.sqlite"
```

Apply:

```bash
python pack_catalog_sync.py sync-json-to-db \
  --packs-root "C:/.../semantic/packs" \
  --db "C:/.../category_meta.sqlite" \
  --apply --backup
```

## 4) Sync DB -> JSON

Use this after editing the DB and wanting to push metadata back into pack files.

Preview:

```bash
python pack_catalog_sync.py sync-db-to-json \
  --packs-root "C:/.../semantic/packs" \
  --db "C:/.../category_meta.sqlite"
```

Apply:

```bash
python pack_catalog_sync.py sync-db-to-json \
  --packs-root "C:/.../semantic/packs" \
  --db "C:/.../category_meta.sqlite" \
  --apply --backup
```

Optional:

- `--no-cleanup-old` keeps old non-canonical source files instead of removing them after writing canonical ones

## Console preview output

The preview plan prints to the command prompt and shows, per item:

- source path
- category
- `cat_id`
- resolution rule used
- destination path
- DB action
- JSON action
- missing fields added
- warnings

This is intended to be readable enough for normal dev use without needing a GUI.

## JSON report output

Add `--report-json some_report.json` to save a machine-readable report containing:

- summary counts
- conflicts
- warnings
- per-file actions

## Typical workflows

## New incoming packs

1. Place the JSON packs anywhere under `packs_root`
2. Give them at least:
   - `_meta.category`
   - `_meta.title`
   - `_meta.notes`
3. Run:

```bash
python pack_catalog_sync.py intake --packs-root "..." --db "..."
```

4. Review the preview
5. Run again with `--apply --backup`

## Manual JSON edits

1. Edit JSON metadata by hand
2. Run `sync-json-to-db`
3. Review
4. Apply

## Manual DB edits

1. Edit the DB row
2. Run `sync-db-to-json`
3. Review
4. Apply

## Backups

When `--backup` is used, the tool stores timestamped copies under:

```text
<parent_of_packs_root>/backups/pack_catalog_sync/
```

## Important scope note

This version syncs category-level metadata and file placement. It does **not** try to make SQLite the canonical storage for every pack entry body.

The DB stores category metadata, pack paths, and entry keys. JSON files still hold the actual pack entry objects.

## Recommended habits

- always preview first
- use `--backup` for apply mode
- use `audit` when unsure which side should win
- use `--trust-db` only when you intentionally want DB authority
- keep human-readable categories stable and meaningful

## Troubleshooting

### "conflicts_detected"

Run the same command without `--apply` and inspect the preview. Typical causes:

- one `cat_id` mapping to multiple categories
- one category mapping to multiple `cat_id` values
- conflicting category decisions under `--strict-category-conflicts`

### file moved unexpectedly

That usually means the file's `_meta.category` resolved to a different canonical path. The path is always derived from the final normalized category.

### notes/title missing on new packs

The tool auto-fills those if absent, but you will get better results if you write them yourself.

## File included in this package

- `pack_catalog_sync.py`: main standalone script
- `README.md`: documentation
