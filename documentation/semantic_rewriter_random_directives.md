# Semantic Rewriter Random Directive System (v2)

# Overview

The Semantic Rewriter now supports advanced runtime randomization directives inside:

```text
%%{ ... }%%
```

These directives allow prompts to dynamically choose:

- random categories
- random keys
- multiple random categories
- multiple random keys from the same category
- rerolls
- mutations
- modifier stacks

This system works entirely at rewrite time inside `rewriter.py`.

---

# Supported Operators

| Operator | Meaning |
|---|---|
| `?` | Random selection |
| `!` | Reroll / exclude current key |
| `~` | Mutation (future semantic mutation support) |
| `+N` | Select multiple categories |
| `+N|` | Select multiple keys from the SAME category |

---

# Basic Random Selection

## Random Category + Random Key

```text
%%{?core.medium}%%
```

Behavior:

1. Finds matching categories under:
   ```text
   core.medium.*
   ```

2. Randomly selects ONE category.

3. Randomly selects ONE key from that category.

---

# Broad Category Randomization

## Randomize Entire Core Tree

```text
%%{?core}%%
```

Possible internal resolution:

```text
core.medium.charcoal=smudged_charcoal
```

or:

```text
core.medium.gouache=flat_gouache
```

or:

```text
core.surface.paper=toned_paper
```

---

# Modifier Tree Randomization

## Example: Eye Modifiers

```text
%%{?appearance.physical.head.eyes.mod}%%
```

Possible results:

```text
appearance.physical.head.eyes.mod.gaze=side_glance
```

or:

```text
appearance.physical.head.eyes.mod.highlight=catchlight
```

or:

```text
appearance.physical.head.eyes.mod.color=blue
```

---

# Multi-Category Random Selection

## Select Multiple Different Categories

```text
%%{+2?appearance.physical.head.eyes.mod}%%
```

Behavior:

1. Randomly selects TWO different categories under:

```text
appearance.physical.head.eyes.mod.*
```

2. Randomly selects ONE key from each.

Example:

```text
appearance.physical.head.eyes.mod.color=blue
appearance.physical.head.eyes.mod.gaze=side_glance
```

Another example:

```text
appearance.physical.head.eyes.mod.highlight=catchlight
appearance.physical.head.eyes.mod.lashes=long_lashes
```

---

# Same-Category Multi-Key Selection

## Multiple Keys From Same Category

```text
%%{+2|?core.medium.ink_drawing}%%
```

Behavior:

1. Resolves ONE category:
   ```text
   core.medium.ink_drawing
   ```

2. Selects TWO different keys from that same category.

Example:

```text
pen_and_ink
scratchy_ink
```

Another example:

```text
technical_ink
crosshatched_ink
```

---

# Multi-Key Modifier Example

```text
%%{+3|?appearance.physical.head.eyes.mod.color}%%
```

Possible picks:

```text
blue
green
amber
```

This is useful for:

- mixed eye effects
- layered modifiers
- stacked textures
- style mixing

---

# Reroll Operator

## Exclude Current Key

```text
%%{!appearance.physical.head.eyes.mod.color=blue}%%
```

Behavior:

- Randomly selects another key
- Excludes `blue`

Possible results:

```text
green
amber
silver
```

---

# Mutation Operator

## Current Behavior

```text
%%{~appearance.physical.head.eyes.mod.color=blue}%%
```

Currently behaves similarly to:

```text
!appearance.physical.head.eyes.mod.color=blue
```

Meaning:

- exclude the current key
- reroll another key

---

# Future Mutation Support

The `~` operator is reserved for future semantic mutation systems.

Planned future schema additions:

```json
{
  "blue": {
    "related": ["cyan", "teal", "silver"],
    "families": ["cool", "bright"]
  }
}
```

This would allow:

```text
~color=blue
```

to prefer semantically related values.

---

# Bare Directives

The parser now supports directives without explicit values.

Valid:

```text
%%{?core}%%
%%{+2?core.medium}%%
%%{+2|?core.medium.ink_drawing}%%
```

Internally these are treated similarly to:

```text
%%{?core=random}%%
```

---

# Runtime Resolution

These directives resolve at rewrite time.

This means:

```text
%%{?core.medium}%%
```

may produce different results each generation.

---

# Preview Rewrite

The Preview Rewrite window fully supports:

- `?`
- `!`
- `~`
- `+N`
- `+N|`

Example:

```text
%%{+2?appearance.physical.head.eyes.mod}%%
```

The rewritten output will show the fully expanded tags.

---

# Generation-Time Random Picks

Generation now records actual semantic random picks into:

```text
SemanticPrompt random picks
```

inside generation metadata / infotext.

Example:

```text
+2?appearance.physical.head.eyes.mod
-> appearance.physical.head.eyes.mod.color=blue
-> appearance.physical.head.eyes.mod.gaze=side_glance
```

This allows reproducibility by copying the resolved values.

---

# Important Difference: Preview vs Generation

Preview Rewrite and Generate are separate rewrite passes.

Meaning:

- Preview may show one random result
- Generate may choose another

The infotext metadata records the actual generation-time selections.

---

# Recommended Usage Patterns

# General Style Variety

```text
%%{?core.medium}%%
```

---

# Strong Visual Variety

```text
%%{+3?core.medium}%%
```

---

# Layered Modifier Systems

```text
%%{+3?appearance.physical.head.eyes.mod}%%
```

---

# Same-Category Layering

```text
%%{+3|?appearance.physical.head.eyes.mod.highlight}%%
```

---

# Controlled Mutation

```text
%%{~appearance.physical.head.eyes.mod.color=blue}%%
```

---

# Forced Reroll

```text
%%{!core.medium.charcoal=vine_charcoal}%%
```

---

# Architectural Notes

The system is implemented entirely inside:

```text
rewriter.py
```

using runtime category/key resolution.

No loader changes were required.

No registry changes were required.

No UI architecture changes were required.

---

# Current Limitations

## Random Resolution Is Runtime-Based

Selections are generated during rewrite execution.

This means:

- results vary between generations
- results are not seed-locked yet

---

## Mutation Is Currently Simple

`~` currently behaves like reroll/exclusion.

Future schema upgrades may support:

- related values
- semantic families
- intelligent mutation neighborhoods

---

# Future Expansion Ideas

Potential future additions:

| Feature | Purpose |
|---|---|
| semantic seeds | reproducible semantic randomization |
| weighted category randomization | bias certain categories |
| weighted key randomization | bias certain keys |
| mutation strength | soft vs hard mutation |
| semantic neighborhoods | related-value mutation |
| category locking | preserve selected categories across generations |

---

# Example Full Prompt

```text
masterpiece, cinematic lighting,
%%{
+2?core.medium,
+3?appearance.physical.head.eyes.mod,
~appearance.physical.head.eyes.mod.color=blue
}%%
```

Possible expansion:

```text
gouache illustration,
smudged charcoal,
side glance,
catchlight,
green eyes
```

with generation metadata recording the exact semantic picks used.
