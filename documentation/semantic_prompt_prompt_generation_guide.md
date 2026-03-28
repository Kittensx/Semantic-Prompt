# How Packs Affect Prompt Generation and Randomization

This document explains how Semantic Prompt packs influence **prompt
generation, randomization, and prompt composition**.

Understanding how packs interact with the generation system will help
contributors design packs that produce **better prompts, more variety,
and fewer conflicts**.

------------------------------------------------------------------------

# 1. What a Pack Represents

A pack represents a **group of related prompt elements** that belong to
the same conceptual category.

Examples:

-   clothing styles
-   lighting styles
-   eye colors
-   poses
-   environments

Each entry in a pack becomes a **candidate option** during prompt
generation.

Example pack:

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

During prompt generation the system may randomly select one entry from
the pack.

Example output:

    green eyes

------------------------------------------------------------------------

# 2. Categories Control Prompt Structure

Categories determine **how packs combine together**.

Example categories:

    appearance.eye_color
    appearance.hair_color
    clothing.garments.top
    clothing.garments.bottom
    environment.weather
    lighting.style

When the prompt generator runs, it can assemble prompts like:

    green eyes, black hair, leather jacket, jeans, rainy weather, cinematic lighting

Because each piece came from a different category.

This is why **clear category design is critical**.

------------------------------------------------------------------------

# 3. Why Packs Should Represent One Concept

Each pack should represent **one type of decision**.

Good packs:

    eye colors
    pants styles
    weather types
    lighting styles

Bad packs:

    pants
    rain
    dramatic lighting

Bad packs reduce randomness quality and cause prompt chaos.

------------------------------------------------------------------------

# 4. Randomization Behavior

Most generators follow this pattern:

1 pack = 1 selection

Example:

    appearance.eye_color → select 1
    appearance.hair_color → select 1
    clothing.garments.bottom → select 1

Result:

    green eyes, brown hair, cargo pants

If a pack contains unrelated items, randomization becomes unpredictable.

------------------------------------------------------------------------

# 5. Pack Size Matters

Very small packs limit variation.

Example:

    eye_color
      blue eyes
      green eyes

Large packs increase randomness quality.

Example:

    eye_color
      blue eyes
      green eyes
      brown eyes
      hazel eyes
      gray eyes
      amber eyes

Recommended size:

**5--30 entries per pack**.

------------------------------------------------------------------------

# 6. Avoid Conflicting Entries

Entries should not conflict with each other.

Bad example:

    blue eyes
    brown eyes
    heterochromia eyes
    closed eyes

Better structure:

    appearance.eye_color
    appearance.eye_state
    appearance.eye_condition

Splitting concepts improves generation quality.

------------------------------------------------------------------------

# 7. Keep Entries Prompt-Friendly

Entries should read naturally inside prompts.

Good:

    leather jacket
    blue eyes
    standing pose
    dramatic lighting

Avoid:

    style of leather jacket clothing item
    person with blue colored eyes

Prompt engines work best with **clean short phrases**.

------------------------------------------------------------------------

# 8. Category Depth Controls Prompt Organization

Category hierarchy helps organize packs.

Example:

    clothing
      garments
        top
        bottom
        outerwear

Which allows generators to build prompts like:

    leather jacket, cargo pants

from different subcategories.

------------------------------------------------------------------------

# 9. Why Consistent Naming Matters

Consistent naming improves:

-   randomization quality
-   category filtering
-   UI browsing
-   prompt readability

Prefer:

    eye_color
    hair_color
    pants_styles
    lighting_styles

Avoid mixing naming styles.

------------------------------------------------------------------------

# 10. Designing Packs for Random Prompt Systems

When designing packs, ask:

Does this pack represent **one clear choice**?

Examples of good prompt decisions:

    eye color
    hair style
    lighting style
    weather
    pose
    camera angle

Each should live in its own pack.

------------------------------------------------------------------------

# 11. What Happens During Prompt Generation

Typical prompt assembly:

1.  Choose packs from selected categories
2.  Randomly select entries
3.  Combine selections into a prompt

Example result:

    green eyes, blonde hair, leather jacket, cargo pants, dramatic lighting, rainy weather

The quality of this prompt depends heavily on **pack design**.

------------------------------------------------------------------------

# 12. Designing Packs for Maximum Variety

To improve prompt diversity:

-   avoid duplicate phrases
-   include a range of styles
-   mix simple and detailed descriptors
-   avoid near-identical entries

Bad:

    blue eyes
    bright blue eyes
    very bright blue eyes

Better:

    blue eyes
    green eyes
    hazel eyes
    amber eyes
    gray eyes

------------------------------------------------------------------------

# 13. Recommended Pack Strategy

A strong prompt system usually contains packs for:

Character features Clothing Accessories Pose Expression Environment
Lighting Camera style Art style

These combine to generate rich prompts.

------------------------------------------------------------------------

# 14. Example Prompt Built from Packs

Example result generated from multiple packs:

    green eyes, long black hair, leather jacket, cargo pants, standing pose, dramatic cinematic lighting, rainy street environment

Each component came from a different pack.

------------------------------------------------------------------------

# 15. Key Takeaways

When creating packs:

✔ One concept per pack\
✔ Clear category structure\
✔ Prompt-friendly entries\
✔ Avoid conflicts\
✔ Include enough entries for variety

Good pack design leads to **better prompts and better random
generation**.
