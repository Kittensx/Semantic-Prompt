# Semantic Prompt Pack Quick Rules

Short reference for pack creation.

------------------------------------------------------------------------

## Pack Format

Every pack must look like:

    {
      "_meta": {...},
      "key": {...}
    }

Entries are **top-level keys**.

Never use:

    "keys": { ... }

------------------------------------------------------------------------

## Required `_meta`

-   category
-   title
-   notes

------------------------------------------------------------------------

## Allowed Entry Fields

-   tags
-   aliases
-   related
-   requires
-   excludes

------------------------------------------------------------------------

## Forbidden Fields

Do not manually add:

-   cat_id
-   schema_version
-   pack_paths
-   generatable

------------------------------------------------------------------------

## Naming Rules

Keys should be:

-   short
-   descriptive
-   lowercase
-   underscore separated

Avoid repeating pack words.

Example:

Pack: sides

Bad:

    side_tie_side

Good:

    side_tie

------------------------------------------------------------------------

## Relationship Syntax

Same pack:

    "related": ["scrunch"]

Other pack:

    "related": ["category:key"]

Example:

    clothing.garments.swimwear.bikini.top.mod.sides:side_tie

------------------------------------------------------------------------

## Entry Example

    "side_tie": {
      "tags": ["side tie bikini bottom"]
    }

------------------------------------------------------------------------

Follow these rules when authoring packs.
