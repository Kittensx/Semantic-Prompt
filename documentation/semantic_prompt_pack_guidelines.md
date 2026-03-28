# Semantic Prompt Pack Creation Guidelines

This guide explains the **minimum requirements for creating new packs**
for the Semantic Prompt system.

The goal is to make pack creation **simple for contributors**, while
allowing the intake tool to automatically normalize metadata, assign
IDs, and register packs in the database.

Only a few fields are required.

------------------------------------------------------------------------

# 1. File Format

Pack files must be:

-   **JSON files**
-   UTF‑8 encoded
-   Valid JSON structure
-   The filename does **not matter** (the intake tool will rename it
    automatically)

Example filename:

pants_styles.json

------------------------------------------------------------------------

# 2. Required `_meta` Fields

Every pack must contain a `_meta` block with **three required fields**.

    _meta:
      category
      title
      notes

Example:

``` json
{
  "_meta": {
    "category": "clothing.garments.bottoms.pants",
    "title": "Pants Styles",
    "notes": "Styles of pants including jeans, cargo pants, leggings, and dress pants."
  }
}
```

------------------------------------------------------------------------

# 3. Category Rules

`category` defines where the pack lives in the taxonomy.

Rules:

-   Use **dot-separated hierarchy**
-   Use **lowercase**
-   Avoid spaces
-   Keep names descriptive but concise

Example:

    clothing.garments.bottoms.pants

Good examples:

    clothing.material
    appearance.eye_color
    environment.weather
    lighting.style
    pose.action

Avoid:

    Clothing.Pants
    pants
    pants styles

------------------------------------------------------------------------

# 4. Pack Entries

Everything outside `_meta` becomes a **pack entry**.

Example:

``` json
{
  "_meta": {
    "category": "clothing.garments.bottoms.pants",
    "title": "Pants Styles",
    "notes": "Styles of pants."
  },

  "jeans": {},
  "cargo pants": {},
  "leggings": {},
  "dress pants": {}
}
```

Entry objects may remain empty.\
The system can add fields later if needed.

------------------------------------------------------------------------

# 5. Fields You Should NOT Include

These are generated automatically by the intake tool.

Do **not** add them manually.

    cat_id
    generator_family
    generator_slot
    generatable
    pack_paths
    schema_version

------------------------------------------------------------------------

# 6. Naming Guidelines

Entry keys should be:

-   short
-   descriptive
-   prompt-friendly

Good examples:

    jeans
    cargo pants
    leather jacket
    blue eyes
    standing pose
    dramatic lighting

Avoid:

    pants style #1
    very cool pants maybe

------------------------------------------------------------------------

# 7. One Category Per Pack

Each pack should represent **one logical concept group**.

Good examples:

    pants styles
    eye colors
    lighting styles
    weather types

Avoid mixing unrelated concepts in the same pack.

Bad example:

    pants
    rain
    dramatic lighting

------------------------------------------------------------------------

# 8. What Happens After Submission

The intake tool will automatically:

-   generate a **cat_id**
-   normalize metadata
-   move the file to the correct category folder
-   register the pack in the database
-   ensure schema compatibility

Example final location:

    packs/clothing/garments/bottoms/pants/cat_xxxxx.json

------------------------------------------------------------------------

# 9. Minimal Pack Template

You can copy this template when creating new packs.

``` json
{
  "_meta": {
    "category": "",
    "title": "",
    "notes": ""
  }
}
```

Example completed pack:

``` json
{
  "_meta": {
    "category": "appearance.eye_color",
    "title": "Eye Colors",
    "notes": "Common eye colors used in character descriptions."
  },

  "blue eyes": {},
  "green eyes": {},
  "brown eyes": {},
  "hazel eyes": {}
}
```

------------------------------------------------------------------------

# 10. Final Checklist

Before submitting a pack:

✔ File extension is `.json`\
✔ `_meta.category` is filled\
✔ `_meta.title` is filled\
✔ `_meta.notes` explains the pack\
✔ Entries are simple and descriptive

That's all that's required.

The system will handle the rest automatically.
