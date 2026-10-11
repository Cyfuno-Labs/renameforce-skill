---
name: renameforce
description: Find Salesforce product names in files, pasted text, or Google Drive documents, verify them against Renameforce rename history, and correct the ones that are out of date. Use when the user mentions Salesforce product names (Pardot, Marketing Cloud, Einstein, Tableau CRM, Agentforce, and so on), asks whether a product name is current or what something is called now, or wants docs, decks, web copy, or READMEs checked or updated after Salesforce renames.
---

# Renameforce

Salesforce renames products often. This skill checks content against the Renameforce
rename database (renameforce.com), reports names that are out of date, and fixes them
the way the user wants.

Paths below are relative to this skill's directory.

## Workflow

1. **Pick the mode** (see Modes). Default is `review`.
2. **Find a working Python yourself; never ask the user.** Try these in order and use the
   first that prints a version of 3.9 or later: `python3 --version`, then
   `python --version`, then `py -3 --version` (the Windows launcher). Judge by the printed
   version, not by whether the command exists: a command that errors, prints nothing, or
   opens an app store is not usable. Use the winning command wherever `<python>` appears
   below, and keep using it for the rest of the session. If none works, use the chat-only
   path in "Without scripts" and tell the user once that you are running in
   reduced-precision mode.
3. **Resolve the data**: run `<python> scripts/get_data.py` (add `--refresh` if the user
   wants the latest). It prints `source`, `generated_at`, and `path`. `source` is `cache`
   (a saved copy under 7 days old, or confirmed unchanged), `live` (fetched just now), or
   `snapshot` (the copy bundled with the skill, used when nothing else worked). The first
   run on a machine is normally `live` because there is no cache yet.
   Always tell the user which data you used, for example "checked against Renameforce data
   as of 2026-10-10 (cache)". If `notes` mention a failure, say that you fell back.
4. **Scan**: `<python> scripts/scan.py --data <path> PATH...` (use `-` to read stdin). A PATH can
   be a file or a folder; folders are walked for text files (`.md`, `.markdown`, `.mdx`,
   `.txt`, `.rst`, `.adoc`, `.html`, `.htm`, `.csv`), skipping dot-folders and
   `node_modules`. Names split across lines or by extra spaces are matched, so `matched` may
   contain a line break. It prints a JSON array. Each finding has `path`, `line`, `column`, `matched`, `product_id`,
   `classification`, `current_name`, `changed_on`, and `reason`. An entry with `skipped` means
   a file was binary or unreadable; report it. Code, URLs, and paths are skipped unless you
   pass `--include-code` at the user's request.
5. **Judge each finding** using `references/matching-rules.md`.
6. **Act according to the mode**, then print the summary.

## Classes

- `current`: matches the present name (or an alias). No action.
- `outdated`: a past name. `current_name` is the replacement and `changed_on` is when the
  name stopped being used.
- `ambiguous`: the name belongs to several products, is a generic word or acronym that
  collides with another meaning, or belongs to a **retired** product (its `reason` says so;
  there is no current name to replace it with). Ambiguous hits are never auto-changed in any
  mode; ask the user, and never offer a retired product's name as a replacement.

A name that was reverted to an earlier name (for example a product renamed and then renamed
back) is `current` when it equals the present name; only the in-between names are `outdated`.

## Context judgment (the script cannot do this)

- **Historical mentions stay.** "In 2019 we migrated from Pardot" or a document dated before
  `changed_on` was correct when written. Flag it; do not change it.
- **Mixed old and new names.** If one document uses both an old name and the current name
  for the same product, treat each old-name use as `outdated` (unless it is historical) and
  mention the inconsistency in the summary so the user can align the whole document.
- **Quoted material and citations stay.** Names inside quotations, release-note titles, or
  cited sources are reported, not edited.
- **Grammar after substitution.** Fix articles ("an Einstein Analytics dashboard" becomes "a CRM Analytics dashboard"),
  possessives, and plurals. Keep the capitalization style of the surrounding text.
- **When unsure, ask.** A wrong silent edit is worse than one extra question.

## Modes

| Mode | Behavior | User says things like |
|---|---|---|
| `report` | List findings with locations and suggested replacements. Edit nothing. | "just check", "don't change anything" |
| `review` (default) | Show each proposed change; apply only the ones the user approves. | nothing needed, "walk me through changes" |
| `apply` | Apply every `outdated` finding you judge safe, then summarize. | "fix them all", "apply without asking" |

A persistent preference may appear in the user's `CLAUDE.md`, `AGENTS.md`, or other project instructions
(for example "RenameForce skill: default to report mode"). Honor it unless the user
asks for something different in this request.

Invariants in every mode: `ambiguous` and historical-context hits are never auto-changed,
and you never claim a clean result without saying what was scanned.

## Findings table

Present findings in every mode with this one table, one row per finding that needs
attention, sorted by file and line:

| Where | Found | Change to | Since | Action |
|---|---|---|---|---|

- **Where**: `file:line`, or slide number or heading for Drive documents.
- **Found**: the text exactly as written.
- **Change to**: the current name, or `—` when there is none (retired or ambiguous).
- **Since**: when the old name stopped being used (`2022-04`), or `—`.
- **Action**: exactly one of **Update** (an `outdated` name to change), **Keep** (historical
  or quoted, so leave it), or **Ask** (ambiguous or retired, needs the user's decision). Add
  the reason in a few words, for example "Keep (historical)" or "Ask (retired)".

Names that are already current get no rows; mention them only as a count in the summary
("12 names already current, no action").

Example:

| Where | Found | Change to | Since | Action |
|---|---|---|---|---|
| sample.md:3 | Pardot | Marketing Cloud Account Engagement | 2022-04 | Update |
| sample.md:7 | Datorama | Marketing Cloud Intelligence | 2020 | Keep (historical) |
| sample.md:5 | Social Studio | — | — | Ask (retired) |

How each mode uses it: `report` prints the table and stops. `review` prints the table and
asks which **Update** rows to apply (refer to rows by **Where**). `apply` makes every
**Update** edit it judges safe and then prints the same table, where **Update** rows are
the ones that were changed.

## End-of-run summary

Always finish with:

- **Data:** source and `generated_at`.
- **Scanned:** the files or text checked.
- **Changed:** each edit (old name, new name, location), or "none".
- **Flagged:** items left for the user, with the reason (historical, ambiguous, quoted).
- **Skipped:** binary or unreadable files, and skipped regions if relevant.

If there are zero findings, say exactly that along with what was scanned and the data date,
so "nothing found" is not mistaken for "not checked".

## Where the content lives

### Local files (filesystem and scripts available)

Run the scripts on the files and edit in place, showing real diffs. Markdown, HTML, text,
and similar formats are supported. For `.docx` and `.pptx`, extract the text and report;
do not edit these in place.

### Without scripts (no Python, or plain chat)

Read `data/names-index.json` instead. Each product lists `current_name`, `aliases`, and
`past_names` with the date each `ended`. Match the pasted text against those names
yourself, classify as above, and return the corrected text. Say once that this is
reduced-precision mode: no exact line and column output, and less consistent on long
documents. Installing Python 3.9 or later restores full checking.

### Google Drive

When a Drive connector is available, Google Docs, Slides, Sheets, and Drive-hosted Office
and PDF files can be checked. Tool names differ between agents and connectors, so this
section describes tools by function; examples in parentheses are names some connectors use.

- **Find the file** with a Drive search tool (for example `search_files`), or use an ID the
  user gave you. Never guess an ID.
- **Read it** with a Drive read tool (for example `read_file_content`), then pass the text to
  `scripts/scan.py` through stdin (or match against `data/names-index.json` without scripts).
- **Locations** are slide number, heading, or surrounding text, not line numbers.
- **Editing:** Drive connectors normally cannot change a document's text; an update tool
  such as `update_file` typically changes only the title and folder. In `review` and
  `apply` modes, give the user exact, grouped replacements ("Pardot" to
  "Marketing Cloud Account Engagement", 7 occurrences, with locations) to run through Docs
  or Slides Find and Replace (Ctrl+H), which preserves all formatting.
- **Optional extras:** offer a Drive copy tool (for example `copy_file`) for a safe working
  copy first. Offer a corrected plain-text copy with a Drive create tool (for example
  `create_file`) only if asked, and warn that layout, images, and slide structure are lost.
  Never modify the original.
- **Check which tools exist** instead of assuming. If a connector exposes in-place text
  replacement, `apply` may use it under the same invariants as everywhere else.

## Limits

- The data reflects what Renameforce has recorded, which can lag official announcements.
  Names the data does not know are left alone.
- This is a naming aid, not legal or trademark advice.
