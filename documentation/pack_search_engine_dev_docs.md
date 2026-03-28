
# Pack Search Engine — Developer Documentation

## Overview

`pack_search_engine.py` is a backend search engine designed to search **Semantic Prompt pack files** and return **ranked promptable entries**.

Its purpose is to allow users (and future UI components) to:

- search pack entries by natural text
- discover available prompt tokens
- rank likely matches
- inspect entry definitions
- copy prompt tokens into prompts (`category:key` or `category=key`)

The engine is designed to be:

- schema tolerant
- ranking driven
- UI-ready
- CLI-testable

This tool replaces the earlier `search_tag_suggester` approach by focusing on **entry discovery and ranking**, not just metadata extraction.

---

# File Location

Recommended location:

```
semantic/tools/pack_search_engine.py
```

Reason:

- It is currently a developer utility tool
- It is first tested via CLI
- UI integration will happen later

---

# Core Design Philosophy

The search engine operates on the concept of **entry-first search**.

Instead of returning pack files, the engine returns **individual prompt keys**.

Example result:

```
clothing.garments.tops.mod.cutouts:double_cutouts
```

Each result corresponds to **one entry inside a pack file**.

---

# Pack Structure Assumptions

The engine assumes pack files follow the Semantic Prompt JSON structure.

Example pack:

```json
{
  "_meta": {
    "category": "clothing.garments.tops.mod.cutouts",
    "title": "Top Cutouts",
    "notes": "",
    "aliases": [],
    "search_tags": [],
    "related_categories": []
  },
  "double_cutouts": {
    "tags": [
      "double cutout top",
      "dual cutout blouse"
    ]
  }
}
```

---

# Required Fields

Minimum pack requirements:

```
_meta.category
entry key
```

Example minimal entry:

```
"double_cutouts": {}
```

---

# Optional Fields

Pack metadata fields:

```
_meta.title
_meta.notes
_meta.aliases
_meta.search_tags
_meta.related_categories
```

Entry fields:

```
tags
aliases
related
requires
excludes
negative
```

The search engine tolerates packs where these fields are missing.

---

# Searchable Fields

## Entry Fields

```
key
entry.tags
entry.aliases
entry.related
entry.requires
entry.excludes
entry.negative
```

## Pack Metadata

```
meta.category
meta.title
meta.notes
meta.aliases
meta.search_tags
meta.related_categories
```

---

# Unknown Fields

If an entry contains unknown fields such as:

```
surface
pattern
finish
placement
```

And the values are strings or lists of strings, they are indexed automatically as:

```
entry.other.<field_name>
```

Example:

```
entry.other.surface
entry.other.pattern
```

This ensures the engine remains future-compatible with new pack schemas.

---

# Search Behavior

Default search mode is forgiving.

The engine automatically:

- ignores case
- normalizes underscores, spaces, and hyphens
- handles plural / singular variations
- allows partial matching

Example query:

```
double cutouts
```

Matches:

```
double_cutouts
double-cutouts
double cutout blouse
```

---

# Normalization Rules

Separators treated as equal:

```
_
-
space
```

Example equivalence:

```
double_cutouts
double cutouts
double-cutouts
```

All normalize to:

```
double cutouts
```

---

# Plural Handling

Plural normalization occurs automatically.

Examples:

```
cutout → cutouts
cutouts → cutout
dress → dresses
```

Plural handling expands matching without requiring duplicate metadata.

---

# Partial Matching

Partial matches are supported.

Examples:

```
cutouts → double_cutouts
double_cut → double_cutouts
close → close_up
```

Partial matches rank lower than exact matches.

---

# Match Case Mode

Optional mode:

```
--match-case
```

Behavior:

1. first attempt literal matching
2. fallback to normalized matching

Example:

```
double_cut
```

Prioritizes:

```
double_cutouts
```

before normalized matches.

---

# Ranking Philosophy

The engine ranks results based on relevance and usability.

Ranking ensures that promptable tokens appear first.

The engine never assumes the top result is correct.

Multiple ranked results are returned.

---

# Default Ranking Priority

Highest → lowest importance:

```
key
entry.aliases
meta.aliases
meta.search_tags
entry.tags
meta.title
meta.notes
entry.related
entry.requires
entry.excludes
entry.negative
meta.related_categories
```

---

# Field Modes

Fields can be configured with three modes:

```
ignored
normal
high
```

Meaning:

| Mode | Behavior |
|------|----------|
| ignored | field not searched |
| normal | default weight |
| high | boosted ranking |

Example CLI override:

```
--field-mode entry.tags=high
```

---

# Search Presets

Presets simplify field configuration.

Available presets:

```
prompt
exact_key
broad
relationships
debug
```

Example:

```
--preset prompt
```

---

## Prompt Search (default)

Prioritizes prompt tokens.

Boosts:

```
key
entry.aliases
entry.tags
```

Ignores:

```
entry.requires
entry.excludes
entry.negative
```

---

## Exact Key Search

Used when the user already knows the key.

Only searches:

```
key
entry.aliases
```

---

## Broad Search

Useful for exploration.

Includes:

```
key
entry.aliases
entry.tags
meta.search_tags
meta.aliases
```

---

## Relationship Search

Focuses on semantic relationships.

Boosts:

```
entry.related
entry.requires
entry.excludes
meta.related_categories
```

---

## Debug Search

Indexes everything.

Used for development and debugging.

---

# Advanced Search Syntax

Advanced mode is optional.

Enabled with:

```
--advanced
```

Allows ranking overrides inside the query.

---

## rank

Boost or reduce field importance.

Example:

```
rank key:2.0
rank entry.tags:1.3
rank meta.search_tags:0.8
```

Values:

```
>1 increase weight
<1 reduce weight
```

---

## ignore

Disable a field completely.

Example:

```
ignore meta.notes
ignore entry.negative
```

Ignored fields:

- produce no matches
- contribute no score

---

## Example Advanced Query

```
cutouts rank key:2.0 ignore meta.notes
```

Parsed as:

```
query = "cutouts"
directives:
    rank key:2.0
    ignore meta.notes
```

---

# Directive Precedence

Order of authority:

```
1 advanced query directives
2 CLI field overrides
3 preset configuration
4 engine defaults
```

---

# CLI Usage

Basic search:

```
python pack_search_engine.py "cutouts" --packs-root PATH
```

Examples:

python pack_search_engine.py "double cutouts" --packs-root ../packs

python pack_search_engine.py "cutout" --packs-root ../packs
```

---

# CLI Options

| Option | Description |
|-------|-------------|
| --packs-root | root pack folder |
| --format | output format (colon or equals) |
| --match-case | enable literal matching |
| --max-results | limit results |
| --show-definitions | show entry payload |
| --preset | select search preset |
| --field-mode | override field mode |
| --advanced | enable advanced syntax |
| --json | output JSON instead of text |

---

# Example Output

```
[1] clothing.garments.tops.mod.cutouts:double_cutouts
    score: 142
    matched fields: key, entry.tags
    reason: normalized exact match
    tags: double cutout top; dual cutout blouse
```

---

# Definition Payload

Each result includes full entry data.

Example:

```
definition:
  category: clothing.garments.tops.mod.cutouts
  key: double_cutouts
  file: packs/clothing/...
  tags:
    - double cutout top
    - dual cutout blouse
```

---

# JSON Output

Enable structured output:

```
--json
```

Useful for UI integration.

---

# UI Integration Plan

The UI search panel will use this engine.

Expected UI behavior:

Single-click result:

1. copy prompt token to clipboard
2. expand definition panel

Displayed token:

```
category:key
```

or

```
category=key
```

based on user preference.

---

# Relationship to Other Tools

This tool replaces:

```
search_tag_suggester.py
```

Differences:

| Tool | Purpose |
|------|---------|
| search_tag_suggester | metadata discovery |
| pack_search_engine | entry search and ranking |

---

# Future Improvements

Planned enhancements:

```
UI search integration
clipboard copy on click
interactive definition viewer
index caching
search performance optimization
semantic similarity ranking
```

---

# Summary

`pack_search_engine.py` provides a powerful, flexible search layer for Semantic Prompt packs.

It supports:

- schema tolerance
- ranking
- advanced search syntax
- field weighting
- prompt token discovery
- UI-ready results

The tool is designed to scale as the pack ecosystem grows.

# Search Tests
- Plural / Singular normalization test
python pack_search_engine.py "cutout" --packs-root ../packs

- Separator normalization test
python pack_search_engine.py "double-cutouts" --packs-root ../packs

- Partial word search
python pack_search_engine.py "cut" --packs-root ../packs

- Alias search

python pack_search_engine.py "blouse cutout" --packs-root ../packs

- Metadata search test
python pack_search_engine.py "cutout tops" --packs-root ../packs

-  Advanced ranking directive
python pack_search_engine.py "cutouts rank key:2.0" --packs-root ../packs --advanced

- Ignore field directive
python pack_search_engine.py "cutouts ignore entry.tags" --packs-root ../packs --advanced

- Exact key search preset
python pack_search_engine.py "double_cutouts" --packs-root ../packs --preset exact_key

- Relationship search preset
python pack_search_engine.py "cutouts" --packs-root ../packs --preset relationships


- JSON output test (for future UI)
python pack_search_engine.py "cutouts" --packs-root ../packs --json

- looking for bugs
python pack_search_engine.py "double cutout blouse" --packs-root ../packs

- stress test
python pack_search_engine.py "double cutouts blouse rank key:2.0 ignore meta.notes" --packs-root ../packs --advanced