# Semantic-Prompt
Semantic Prompt is a compositional prompt engine that turns structured pack libraries into scalable, directive-driven prompt systems. It enables controlled randomness, semantic grouping, and extensible architecture for advanced AI creativity and structured generative workflows.

# Semantic Prompt (%%...%%) --- JSON Pack + Trigger-Based Prompt Expansion (A1111)

Semantic Prompt is an Automatic1111 extension that expands *only* the
text inside `%% ... %%` blocks into structured prompt tags using:

-   JSON "packs" (category dictionaries like `medium.json`,
    `lighting.json`, etc.)
-   Trigger phrases (keywords mapped to pack selections)

Everything outside of `%% ... %%` remains untouched.

------------------------------------------------------------------------

## Quick Install (Automatic1111)

1.  Clone or download this repository into:
    stable-diffusion-webui/extensions/`<this-repo>`{=html}/

2.  Ensure the extension contains:

    -   scripts/semantic_prompt.py
    -   semantic/
    -   - loaders.py
        - rewriter.py
        -   packs/
        -   triggers/triggers.json

3.  Open Packs folder and unzip
4.  Restart A1111.

You will see "Semantic Prompt (%%...%%)" in the Script dropdown.

------------------------------------------------------------------------

# The Core Idea

Instead of writing long structured prompts manually:

watercolor painting, soft edges, paper texture, dusk lighting, muted
colors

You can write:

portrait, %%a watercolor valley at dusk with rain%%, film grain

The extension: 1. Scans only inside %%...%% 2. Matches trigger phrases
3. Expands them using JSON packs 4. Optionally adds negative tags

Everything outside remains exactly as you typed it.

------------------------------------------------------------------------

# Basic Syntax

## Plain Block (Trigger-Based)

%%a watercolor valley at dusk with rain%%

Multi-word phrases are matched directly. Single words use word
boundaries.

------------------------------------------------------------------------

## Explicit Directives (Full Control)

%%{medium=watercolor, lighting=softbox, palette=muted} a rainy street%%

Directives are comma-separated category=value pairs. Multiple values
allowed using \| or ;

------------------------------------------------------------------------

## Weighted Tags

%%{subject=beach:1.2, lighting=neon:1.1}%%

------------------------------------------------------------------------

## Negative Directives

%%{negative+=blurry\|lowres\|jpeg artifacts}%%

Negatives from packs are only appended if "Inject negatives" is enabled.

------------------------------------------------------------------------

# How Triggers Work

Triggers live in: semantic/triggers/triggers.json

Example:

{ "watercolor": { "medium": { "pick": "watercolor", "priority": 100 } }
}

pick selects the highest priority match. add stacks multiple matches.

------------------------------------------------------------------------

# How JSON Packs Work

Each pack file represents a category such as: - medium.json -
lighting.json - subject.json

Example entry:

"watercolor": { "tags": \["watercolor painting", "paper texture"\],
"style": \["soft edges", "paint bleed"\], "negative": \["photo",
"hyperrealistic"\] }

tags = primary output tags\
cross-category helpers = inject into other conceptual areas\
negative = optional negative tags

------------------------------------------------------------------------

# Advanced Pack Features

## requires --- Automatic Chaining

requires allows one entry to automatically include another.

Example:

"stormy sky": { "tags": \["dark storm clouds"\], "requires":
\["lighting:dramatic", "palette:desaturated"\] }

If stormy sky is selected, lighting:dramatic and palette:desaturated are
also applied.

Supports recursive expansion with cycle protection.

In simple terms: requires lets you build smart modular styling blocks.

------------------------------------------------------------------------

## excludes --- Conflict Cleanup

Example:

"night scene": { "tags": \["dark night sky"\], "excludes": \["bright
daylight", "sunny sky"\] }

Excludes remove conflicting generated tags. Only applied when "Apply
excludes filtering" is enabled.

In simple terms: excludes prevent visual contradictions.

------------------------------------------------------------------------

## Cross Expansion Mode

Some pack entries include cross-category helpers like lighting or
palette.

Inline mode (default): Cross-category tags stay grouped with the
originating category.

Bucket mode: Cross-category tags are emitted into their proper category
sections.

Inline = grouped together\
Bucket = separated by category

This affects organization, not what tags are applied.

------------------------------------------------------------------------
## Category Checkboxes (Why You Might Disable One)

The UI includes a list of detected categories (subject, medium, lighting, palette, etc.) with checkboxes.

These checkboxes control whether a category is allowed to participate in expansion.

If a category is unchecked:

- Triggers will not apply entries from that category.
- Directives targeting that category will be ignored.
- Cross-category expansions will not emit tags into that category.

---

### Why Would You Disable a Category?

Semantic Prompt is designed to intelligently chain related styling together. However, there are real creative reasons to temporarily disable parts of the system.

#### 1. Preserve Manual Control

You may want to manually control lighting while still allowing medium and palette to auto-expand.

Example:

You want:
- watercolor texture
- automatic palette suggestions

But you want to manually type:
- rim lighting
- cinematic shadows

In that case, disable the **lighting** category.  
Now Semantic Prompt will not override or inject lighting tags.

---

#### 2. Prevent Over-Styling

If you are testing composition or subject variations, you may want to freeze style-related categories.

Disabling categories lets you isolate:

- Only subject expansion
- Only environment logic
- Only composition structure

This is especially useful when tuning prompts for reproducibility.

---

#### 3. Debugging / Pack Testing

When building or debugging packs:

- Disable everything except the category you are editing.
- Confirm exactly what it emits.
- Then re-enable others.

This makes pack behavior easier to reason about.

---

#### 4. Controlled Chaining

Even though `requires` and cross-expansion features allow packs to intelligently chain together, category checkboxes act as guardrails.

They let you decide:

- Which conceptual areas are allowed to auto-adjust
- Which areas remain strictly manual

In simple terms:

Semantic Prompt can think for you —  
but the category checkboxes let you decide *where* it is allowed to think.

---

### Important Note

Disabling a category does not break packs.

It simply prevents that category from emitting tags during rewrite.

You can re-enable it at any time.

------------------------------------------------------------------------
# Output Ordering

Default order:

subject, medium, composition, lighting, palette, quality

You can: - Use default order - Provide a custom order - Randomize per
generation

Unlisted categories are appended automatically.

------------------------------------------------------------------------

# Strict Mode

Normal mode: - Applies directives - Applies triggers

Strict mode: - Applies only explicit directives - Ignores triggers

Recommended for reproducible results.

------------------------------------------------------------------------

# Multiple Blocks

portrait, %%watercolor neon city%%, %%film grain%%, sharp focus

Each block is rewritten independently.

------------------------------------------------------------------------

# Live Pack Editor

The UI allows: - Loading and saving pack entries - Automatic .bak
backups - Live reloading

------------------------------------------------------------------------

# JSON Validation Tool (fix_json)

Detects malformed JSON pack files.

Basic usage: python fix_json.py packs

Recursive scan: python fix_json.py packs --recursive

Exit codes: 0 = no issues 1 = errors found 2 = folder not found

------------------------------------------------------------------------

# Version Notes

LoRA helper features are currently experimental and not part of the
supported workflow in this release.
