# Semantic Prompt Pack Authoring Specification

Version: 1.0

This document defines the canonical structure and authoring rules for
Semantic Prompt pack files.

It is the authoritative reference for:

-   pack file structure
-   `_meta` metadata
-   entry formatting
-   naming conventions
-   cross-pack references
-   mod pack design

All pack authoring tools, AI assistants, and contributors should follow
this specification.

------------------------------------------------------------------------

# 1. Purpose

Semantic Prompt packs define reusable prompt components used to generate
structured prompts.

Each pack represents a category of related prompt keys.

Examples:

-   clothing.garments.swimwear.bikini.bottom.mod.sides
-   appearance.hair.color
-   pose.hand

Packs are simple JSON files.

Each pack contains:

-   a `_meta` section
-   pack entries (keys)

------------------------------------------------------------------------

# 2. Minimal Valid Pack

The smallest valid pack is:

``` json
{
  "_meta": {
    "category": "example.category",
    "title": "Example Pack",
    "notes": "Example description."
  },
  "example_key": {}
}
```

Rules:

-   `_meta` must exist
-   entries exist at the top level
-   entries are JSON objects

------------------------------------------------------------------------

# 3. Pack Structure

General format:

``` json
{
  "_meta": {...},
  "entry_key": {...},
  "entry_key_2": {...}
}
```

Important:

Entries are **not nested inside a `keys` field**.

Incorrect:

``` json
{
  "keys": { ... }
}
```

Correct:

``` json
{
  "entry_name": {...}
}
```

------------------------------------------------------------------------

# 4. `_meta` Fields

Required fields:

  field      description
  ---------- -----------------------------
  category   canonical category path
  title      human readable pack name
  notes      description of pack purpose

Optional fields:

  field              description
  ------------------ ------------------------------
  generator_family   generator grouping
  generator_slot     slot name used by generators

Generated fields (DO NOT AUTHOR):

-   cat_id
-   schema_version
-   pack_paths
-   generatable

These are populated by sync tools.

------------------------------------------------------------------------

# 5. Pack Entries

Each entry is a JSON object.

Minimal entry:

``` json
"side_tie": {}
```

Entry with tags:

``` json
"side_tie": {
  "tags": ["side tie bikini bottom"]
}
```

Entries represent **prompt fragments**.

------------------------------------------------------------------------

# 6. Supported Entry Fields

Allowed fields:

  field      purpose
  ---------- ----------------------------------------
  tags       prompt tags inserted during generation
  aliases    alternative names
  related    stylistic relationships
  requires   dependency relationships
  excludes   incompatibilities

Example:

``` json
"side_tie": {
  "tags": ["side tie bikini bottom"],
  "aliases": ["tie_side"],
  "related": [
    "clothing.garments.swimwear.bikini.top.mod.sides:side_tie"
  ]
}
```

------------------------------------------------------------------------

# 7. Relationship Reference Syntax

References may use three forms.

### Same pack

    "related": ["scrunch"]

### Category reference

    "related": ["clothing.garments.swimwear.bikini.top.mod.sides:side_tie"]

### cat_id reference

    "related": ["cat_12345:side_tie"]

------------------------------------------------------------------------

# 8. Naming Conventions

Keys must follow these rules:

-   lowercase
-   underscore separated
-   short and memorable
-   avoid repeating pack concept

Example:

Pack: `bikini.bottom.mod.sides`

Bad:

    side_tie_side

Good:

    side_tie

Bad:

    tie

Too vague.

Good:

    side_tie

Specific and clear.

------------------------------------------------------------------------

# 9. Mod Pack Design

Mod packs describe **variations of a base item**.

Example:

    clothing.garments.swimwear.bikini.bottom.mod.sides

Typical mod categories:

-   sides
-   waistband
-   front
-   back
-   edges
-   materials
-   decorations

Each pack should represent **one concept only**.

Avoid mixing concepts.

Bad:

    front_and_back_features

Good:

    front
    back

------------------------------------------------------------------------

# 10. Good vs Bad Examples

### Bad Entry

``` json
"tie": {
  "description": "Sides tied together."
}
```

Problems:

-   vague key
-   unsupported field
-   missing tags

------------------------------------------------------------------------

### Good Entry

``` json
"side_tie": {
  "tags": ["side tie bikini bottom"]
}
```

------------------------------------------------------------------------

# 11. Authoring Checklist

Before committing a pack:

-   `_meta` exists
-   category is correct
-   entries are top-level
-   entries are objects
-   no `keys` container
-   generated fields removed
-   names follow conventions
-   relationships valid

------------------------------------------------------------------------

# 12. Templates

## Minimal Pack

``` json
{
  "_meta": {
    "category": "example.category",
    "title": "Example",
    "notes": "Example pack."
  }
}
```

------------------------------------------------------------------------

## Pack With Entries

``` json
{
  "_meta": {
    "category": "example.category",
    "title": "Example",
    "notes": "Example pack."
  },
  "example": {
    "tags": ["example"]
  }
}
```

------------------------------------------------------------------------

End of specification.
