# Semantic Prompt Category Taxonomy Guide

This guide explains how categories should be structured in the Semantic
Prompt system. A well-designed taxonomy ensures packs remain organized,
scalable, and useful for prompt generation and filtering.

------------------------------------------------------------------------

# 1. What a Category Represents

A category represents a **concept group** used to organize packs and
guide prompt composition.

Example categories:

appearance.eye_color\
appearance.hair_style\
clothing.garments.top\
clothing.garments.bottom\
environment.weather\
lighting.style

Each category should represent **one type of prompt decision**.

------------------------------------------------------------------------

# 2. Dot-Based Hierarchy

Categories use a **dot-separated hierarchy**.

Example:

clothing.garments.bottom.pants

This becomes the folder structure:

packs/clothing/garments/bottom/pants/

This structure makes it easy to:

-   browse packs
-   filter categories
-   group related packs
-   expand taxonomy over time

------------------------------------------------------------------------

# 3. Recommended Top-Level Domains

The system works best when categories fall into consistent high-level
groups.

Recommended top-level categories:

appearance\
clothing\
accessories\
pose\
expression\
environment\
lighting\
camera\
art_style\
composition

These cover most prompt-generation needs.

------------------------------------------------------------------------

# 4. Category Depth

Most categories should be **2--4 levels deep**.

Example:

appearance.eye_color\
clothing.garments.top.shirts\
environment.weather.rain\
lighting.style.cinematic

Avoid overly deep structures.

Bad example:

appearance.face.eyes.color.basic.human

------------------------------------------------------------------------

# 5. Category Naming Rules

Categories should follow these rules:

-   lowercase only
-   no spaces
-   use underscores if needed
-   descriptive but concise

Example:

appearance.eye_color

Avoid:

Appearance.Eye Color

------------------------------------------------------------------------

# 6. Keep Categories Stable

Once categories are widely used, changing them can require:

-   moving pack files
-   updating database records
-   rebuilding indexes

Try to keep category names stable once established.

------------------------------------------------------------------------

# 7. Avoid Overlapping Concepts

Categories should not overlap heavily.

Bad design:

appearance.eyes\
appearance.eye_color

Better:

appearance.eye_color\
appearance.eye_shape\
appearance.eye_condition

Each category should represent a **distinct decision point**.

------------------------------------------------------------------------

# 8. Expanding the Taxonomy

When adding new categories:

Ask:

1.  Does this concept already exist?
2.  Can it fit within an existing hierarchy?
3.  Does it represent a clear prompt decision?

Example expansion:

clothing\
clothing.garments\
clothing.garments.top\
clothing.garments.bottom

------------------------------------------------------------------------

# 9. Examples of Good Category Trees

Example clothing tree:

clothing\
clothing.garments\
clothing.garments.top\
clothing.garments.bottom\
clothing.outerwear

Example appearance tree:

appearance\
appearance.eye_color\
appearance.hair_color\
appearance.hair_style\
appearance.skin_tone

------------------------------------------------------------------------

------------------------------------------------------------------------

# 10. Modifier Branches (`.mod`) for Component Parts

Some categories represent **pieces of a larger concept rather than a
full standalone prompt concept**.

In these cases, the category should use a **`.mod` branch**.

`.mod` indicates that the pack contains **modifiers, components, or
sub-parts of a larger whole** rather than a complete concept.

### When to Use `.mod`

Use `.mod` when the pack contains elements that **modify or build a
larger object**.

Examples include:

-   parts of clothing items
-   makeup attributes
-   structural components
-   stylistic modifiers

Examples:

    appearance.makeup.lipstick.mod.color
    appearance.makeup.lipstick.mod.application
    appearance.lips.mod.shape
    appearance.lips.mod.texture

    clothing.garments.bottoms.pants.mod.closure
    clothing.garments.bottoms.pants.mod.length
    clothing.garments.bottoms.pants.mod.seam

These packs describe **features of the object**, not the object itself.

### Why `.mod` Exists

Using `.mod` helps separate:

Whole concepts

    appearance.makeup.lipstick
    clothing.garments.bottoms.pants
    appearance.lips

from their component attributes

    appearance.makeup.lipstick.mod.color
    appearance.makeup.lipstick.mod.application
    clothing.garments.bottoms.pants.mod.closure
    appearance.lips.mod.shape

This keeps the taxonomy clear and prevents modifier packs from being
mistaken for standalone categories.

### Naming Rules for Modifier Categories

Modifier branches should follow this format:

    <base_concept>.mod.<modifier>

Example:

    appearance.makeup.lipstick.mod.color
    appearance.makeup.lipstick.mod.finish
    appearance.makeup.lipstick.mod.application

Avoid using plural forms such as:

    .mods
    .modifiers

The system standard uses **`mod` (singular)**.

### When NOT to Use `.mod`

Do **not** use `.mod` when the category already represents a standalone
concept.

Correct:

    appearance.eye_color
    appearance.hair_color
    lighting.style
    environment.weather

Incorrect:

    appearance.eyes.mod.color
    appearance.hair.mod.color

Eye color is already a primary concept, not a modifier of another
category.

### Example Structure with `.mod`

Example makeup taxonomy:

    appearance
    appearance.makeup
    appearance.makeup.lipstick
    appearance.makeup.lipstick.mod.color
    appearance.makeup.lipstick.mod.application
    appearance.makeup.lipstick.mod.finish

Example clothing taxonomy:

    clothing
    clothing.garments
    clothing.garments.bottoms
    clothing.garments.bottoms.pants
    clothing.garments.bottoms.pants.mod.length
    clothing.garments.bottoms.pants.mod.closure
    clothing.garments.bottoms.pants.mod.material

This approach allows complex items to be **assembled from modular
attributes** while preserving a clean taxonomy.

# 11. Categories and Prompt Generation

Categories help prompt generators decide:

-   which packs to sample
-   how many attributes to combine
-   how to balance prompt composition

Example prompt:

green eyes, black hair, leather jacket, cargo pants, rainy weather,
cinematic lighting

Each component came from a different category.

------------------------------------------------------------------------

# 12. Avoid Category Explosion

Too many tiny categories can make the system hard to manage.

Example problem:

appearance.eye_color.blue\
appearance.eye_color.green

These should instead be entries within a single pack.

Correct structure:

appearance.eye_color

Entries:

blue eyes\
green eyes\
brown eyes

------------------------------------------------------------------------

# 13. Category Review Process

When new packs are submitted:

Check:

-   category is well named
-   hierarchy makes sense
-   category does not duplicate an existing one

If needed, adjust the category before importing.

------------------------------------------------------------------------

# 14. Long-Term Taxonomy Stability

As the project grows:

-   avoid renaming categories frequently
-   expand hierarchies gradually
-   keep naming conventions consistent

A stable taxonomy helps the system scale to hundreds or thousands of
packs.

------------------------------------------------------------------------

# 15. Quick Category Checklist

Before submitting a new pack:

✔ Category uses dot hierarchy\
✔ Category is lowercase\
✔ Category represents one concept\
✔ Category fits the existing taxonomy

------------------------------------------------------------------------

A well-structured taxonomy is the foundation of a powerful prompt
generation system.
