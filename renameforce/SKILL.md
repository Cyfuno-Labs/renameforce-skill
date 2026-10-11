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
2. **Check that Python is available**: `python3` or `python`, version 3.9 or later. If it
   is not, use the chat-only path in "Without scripts" and tell the user once that you are
   running in reduced-precision mode.
3. **Resolve the data**: run `python scripts/get_data.py` (add `--refresh` if the user wants
   the latest). It prints `source` (`cache`, `live`, or `snapshot`), `generated_at`, and `path`.
   Always tell the user which data you used, for example "checked against Renameforce data
   as of 2026-10-10 (cache)". If `notes` mention a failure, say that you fell back.
4. **Scan**: `python scripts/scan.py --data <path> FILE...` (use `-` to read stdin). It prints a
   JSON array. Each finding has `path`, `line`, `column`, `matched`, `product_id`,
   `classification`, `current_name`, `changed_on`, and `reason`. An entry with `skipped` means
   a file was binary or unreadable; report it. Code, URLs, and paths are skipped unless you
   pass `--include-code` at the user's request.
5. **Judge each finding** using `references/matching-rules.md`.
6. **Act according to the mode**, then print the summary.

## Classes

- `current`: matches the present name (or an alias). No action.
- `outdated`: a past name. `current_name` is the replacement and `changed_on` is when the
  name stopped being used.
- `ambiguous`: the name belongs to several products, is a generic word, or is a name that was
  reused or reverted. Ambiguous hits are never auto-changed in any mode; ask the user.

## Context judgment (the script cannot do this)

- **Historical mentions stay.** "In 2019 we migrated from Pardot" or a document dated before
  `changed_on` was correct when written. Flag it; do not change it.
- **Quoted material and citations stay.** Names inside quotations, release-note titles, or
  cited sources are reported, not edited.
- **Grammar after substitution.** Fix articles ("a Pardot" becomes "an Account Engagement"),
  possessives, and plurals. Keep the capitalization style of the surrounding text.
- **When unsure, ask.** A wrong silent edit is worse than one extra question.

## Modes

| Mode | Behavior | User says things like |
|---|---|---|
| `report` | List findings with locations and suggested replacements. Edit nothing. | "just check", "don't change anything" |
| `review` (default) | Show each proposed change; apply only the ones the user approves. | nothing needed, "walk me through changes" |
| `apply` | Apply every `outdated` finding you judge safe, then summarize. | "fix them all", "apply without asking" |

A persistent preference may appear in the user's `CLAUDE.md` or project instructions
(for example "RenameForce skill: default to report mode"). Honor it unless the user
asks for something different in this request.

Invariants in every mode: `ambiguous` and historical-context hits are never auto-changed,
and you never claim a clean result without saying what was scanned.

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
and PDF files can be checked.

- **Find the file** with `search_files` (or use an ID the user gave you). Never guess an ID.
- **Read it** with `read_file_content`, then pass the text to `scripts/scan.py` through stdin
  (or match against `data/names-index.json` without scripts).
- **Locations** are slide number, heading, or surrounding text, not line numbers.
- **Editing:** Drive connectors normally cannot change a document's text (`update_file`
  changes only the title and folder). In `review` and `apply` modes, give the user exact,
  grouped replacements ("Pardot" to "Account Engagement", 7 occurrences, with locations) to
  run through Docs or Slides Find and Replace (Ctrl+H), which preserves all formatting.
- **Optional extras:** offer `copy_file` for a safe working copy first. Offer a corrected
  plain-text copy with `create_file` only if asked, and warn that layout, images, and slide
  structure are lost. Never modify the original.
- **Check which tools exist** instead of assuming. If a connector exposes in-place text
  replacement, `apply` may use it under the same invariants as everywhere else.

## Limits

- The data reflects what Renameforce has recorded, which can lag official announcements.
  Names the data does not know are left alone.
- This is a naming aid, not legal or trademark advice.
