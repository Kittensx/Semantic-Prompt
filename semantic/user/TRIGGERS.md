# Semantic Prompt --- Triggers System

## What are Triggers?

Triggers are **automatic keyword detectors** used by the Semantic Prompt
system.

When a user writes a normal sentence prompt, the system scans the text
for specific words or phrases.\
If a trigger phrase is found, the system **injects additional prompt
tags automatically**.

This allows natural language prompts like:

    girl in a red bikini walking on the beach

to automatically expand into richer structured prompts without the user
needing to manually type tags.

Example expansion:

    girl in a red bikini walking on the beach
    → triggers detect: bikini
    → inject clothing.swimwear.bikini_top tags
    → inject clothing.swimwear.bikini_bottom tags

------------------------------------------------------------------------

# How Trigger Matching Works

The trigger engine performs two types of matches:

### 1. Phrase triggers

Multi‑word phrases are matched using substring detection.

Example:

    "high heels"

Matches:

    girl wearing high heels

------------------------------------------------------------------------

### 2. Single word triggers

Single words are matched using **word boundaries** to avoid false
matches.

Example:

Trigger:

    rain

Matches:

    rain falling

But **will NOT match**:

    brain
    train

because the system uses regex word boundaries.

------------------------------------------------------------------------

# Trigger Injection

Triggers usually map to categories or specific semantic pack entries.

Example:

    "bikini": {
      "categories": [
        "clothing.swimwear.bikini_top",
        "clothing.swimwear.bikini_bottom"
      ]
    }

When the word **bikini** appears in the prompt:

1.  The system finds the trigger
2.  The trigger injects the related semantic categories
3.  The semantic system expands them into tags

------------------------------------------------------------------------

# Trigger File Locations

The system loads triggers from multiple folders:

    semantic/triggers/
    semantic/user/triggers/
    semantic/addons/<addon_name>/triggers/

Load order priority:

1.  Core triggers
2.  Addon triggers
3.  User triggers (override)

User triggers override previous definitions.

------------------------------------------------------------------------

# Example Use Cases

Triggers can be used for:

### Clothing detection

    bikini
    dress
    hoodie
    jacket

### Location hints

    beach
    school
    bedroom
    bathroom

### Pose hints

    sitting
    kneeling
    lying down

### Character archetypes

    princess
    warrior
    witch

------------------------------------------------------------------------

# Best Practices

### Keep triggers simple

Triggers should be **common words people naturally type**.

Good:

    bikini
    dress
    boots

Bad:

    female_swimwear_upper_body_garment

------------------------------------------------------------------------

### Avoid overly generic triggers

Bad examples:

    girl
    person
    human

These would trigger too often.

------------------------------------------------------------------------

# Example Workflow

User prompt:

    girl relaxing at the beach wearing a bikini

Detected triggers:

    beach
    bikini

Injected semantic packs:

    location.beach
    clothing.swimwear.bikini_top
    clothing.swimwear.bikini_bottom

Final prompt expansion uses those categories to generate rich prompt
tags.

------------------------------------------------------------------------

# Summary

Triggers allow the Semantic Prompt engine to:

• understand natural language prompts\
• automatically expand prompts with structured semantic tags\
• connect user text to your pack ecosystem

They are a lightweight **semantic bridge** between natural language and
pack categories.
