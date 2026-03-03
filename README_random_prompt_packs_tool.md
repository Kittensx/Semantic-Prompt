# random_prompt_packs

Bundled CLI tool for exploring this project's JSON pack library.

This tool scans the `packs/` directory, applies optional
directory/category filters, and generates randomized directive blocks
like:

    %%{subject=1girl, lighting=noir, palette=muted, style_manga=clean_lineart}%%

It is designed for exploration, testing, and combinatorial prompt
discovery.

------------------------------------------------------------------------

## Overview

The tool works by:

1.  Scanning a packs root directory (default: `../packs`)
2.  Loading all JSON packs (unless filtered)
3.  Applying directory/category restrictions
4.  Randomly selecting keys per category
5.  Outputting one or more `%%{...}%%` directive blocks

It is not intended to function as a standalone prompt generator --- it
relies on this project's pack structure.

## Content responsibility
This tool outputs tags from user-provided pack files. Some packs may contain adult, sensitive, or platform-restricted content.

The tool does not guarantee compliance with any platform rules. You are responsible for:
- Using appropriate packs for your target platform
- Following applicable laws and policies
- Reviewing generated prompts before use

------------------------------------------------------------------------

# Command Line Arguments

## Core Arguments

### `--packs-root`

Root folder containing JSON packs.

Default:

    ../packs

Example:

    --packs-root packs

------------------------------------------------------------------------

### `--total`

Total number of selections per generated prompt.

Default:

    --total 6

------------------------------------------------------------------------

### `--prints`

Number of prompts to generate.

Default:

    --prints 1

------------------------------------------------------------------------

### `--max-per-category`

Maximum number of selections from the same category per prompt.

Default:

    --max-per-category 2

------------------------------------------------------------------------

### `--out`

Write prompts to a text file (blank line separated).

Example:

    --out prompts.txt

------------------------------------------------------------------------

### `--no-print`

Suppress console output.

Useful when only writing to file.

------------------------------------------------------------------------

## Category Control

### `--use`

Restrict generation to specific category names.

Matches `_meta.category` or filename stem.

Example:

    --use subject lighting palette style_manga

If omitted, all categories are eligible.

------------------------------------------------------------------------

### `--include-min`

Categories that must appear at least once (if available).

Example:

    --include-min subject lighting

------------------------------------------------------------------------

### `--include-any`

Preferred pool for filling remaining selections.

Example:

    --include-any lighting palette

------------------------------------------------------------------------

### `--other-random`

Force this many selections from categories outside `include-min` and
`include-any`.

Example:

    --other-random 2

------------------------------------------------------------------------

### `--exclude`

Exclude specific categories by name.

Example:

    --exclude props_background fetish_shibari

------------------------------------------------------------------------

## Directory Blocking

### `--deny-dir`

Block entire directories under packs root.

Matches directory names as path segments.

Example:

    --deny-dir nsfw fetish underwear

This skips any JSON file located under folders with those names.

This is the most reliable way to block large groups of packs.

------------------------------------------------------------------------

## Safety Controls

### `--safe`

Enable best-effort filtering of explicitly named adult/fetish
categories.

This is a name-based denylist and not a guarantee of compliance.

For strict control, prefer `--deny-dir`.

------------------------------------------------------------------------

## Subject Handling

### `--no-require-subject`

Do not force a subject selection.

By default, the tool attempts to include one item from the subject
category.

------------------------------------------------------------------------

### `--subject-category`

Specify which category name should be treated as subject.

Default:

    subject

Example:

    --subject-category character_main

------------------------------------------------------------------------

## Utility

### `--list-categories`

Print available category names (after directory filtering) and exit.

Example:

    python tools/random_prompt_packs.py --list-categories

------------------------------------------------------------------------

# Basic Use Cases

## 1. Generate 10 completely random prompts

    python tools/random_prompt_packs.py --prints 10

------------------------------------------------------------------------

## 2. Generate 25 prompts and save to file

    python tools/random_prompt_packs.py --prints 25 --out prompts.txt

------------------------------------------------------------------------

## 3. Only use a subset of categories

    python tools/random_prompt_packs.py --use subject lighting palette --prints 20

------------------------------------------------------------------------

## 4. Block NSFW directories

    python tools/random_prompt_packs.py --deny-dir nsfw fetish --prints 25

------------------------------------------------------------------------

# Intermediate Use Cases

## 5. Ensure subject and lighting are always present

    python tools/random_prompt_packs.py --include-min subject lighting --prints 20

------------------------------------------------------------------------

## 6. Favor lighting and palette for aesthetic exploration

    python tools/random_prompt_packs.py --include-any lighting palette --total 8 --prints 20

------------------------------------------------------------------------

## 7. Limit category repetition

    python tools/random_prompt_packs.py --max-per-category 1 --total 6 --prints 15

------------------------------------------------------------------------

# Advanced Use Cases

## 8. Structured exploration with forced diversity

    python tools/random_prompt_packs.py --include-min subject --include-any lighting palette --other-random 2 --total 8 --prints 30

------------------------------------------------------------------------

## 9. Strict controlled subset testing

    python tools/random_prompt_packs.py --use subject lighting palette style_manga composition --deny-dir experimental --max-per-category 1 --total 6 --prints 50 --out controlled_test.txt

------------------------------------------------------------------------

## 10. "Safe-ish" exploration mode

    python tools/random_prompt_packs.py --safe --deny-dir nsfw fetish --prints 25

Note: Safety filtering is name-based. Review prompts before use.

------------------------------------------------------------------------

# Recommended Workflow

-   Organize packs into meaningful directories
-   Use `--deny-dir` for large content blocks
-   Use `--use` for focused testing
-   Use `--include-min` for structural anchors
-   Use `--out` when generating large batches

------------------------------------------------------------------------

# Notes on Content Responsibility

The tool generates directives from user-authored pack files.

Some packs may contain adult, sensitive, or platform-restricted content
depending on how they are structured.

The tool does not guarantee compliance with platform policies.

You are responsible for selecting appropriate directories, reviewing
generated prompts, and ensuring lawful and compliant use.
