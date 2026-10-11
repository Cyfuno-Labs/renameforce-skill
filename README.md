# renameforce-skill

A Claude Skill that finds Salesforce product names in your content, checks them
against [Renameforce](https://renameforce.com) rename history, and fixes the ones
that are out of date.

Salesforce renames products constantly. Ask your Claude agent to check a README, a
deck, web copy, or a Google Doc and it will tell you which names are stale, what they
are called now, and since when.

## What it does

1. **Finds** product names, old names, and common abbreviations in your content.
2. **Verifies** each against the Renameforce database.
3. **Fixes** outdated names, the way you choose: report only, review each change, or
   apply everything safe.

It never silently rewrites historical references ("we migrated from Pardot in 2019"),
quotations, or ambiguous names. Those are flagged for you.

It also recognizes old abbreviations. Short names that come from earlier product names
(for example SFMC for Salesforce Marketing Cloud) are marked as legacy aliases in the data,
so they are reported as outdated rather than current.

**Updating:** if you installed the skill before legacy aliases existed, update your copy.
The data it downloads now includes `legacy_aliases`, which an older copy ignores, so an
old abbreviation such as SFMC would produce no finding at all. Re-copy the `renameforce/`
folder from this repository to update.

## Install

**Claude Code**

Copy the `renameforce/` folder (the one containing `SKILL.md`) into your skills
directory, for example `~/.claude/skills/renameforce/` for all projects or
`.claude/skills/renameforce/` inside one project.

```bash
git clone https://github.com/Cyfuno-Labs/renameforce-skill.git
cp -r renameforce-skill/renameforce ~/.claude/skills/
```

**claude.ai**

Zip the `renameforce/` folder and upload it under Settings, Capabilities, Skills.

## Other agents

The skill uses the open `SKILL.md` format (a folder with a `SKILL.md` that has `name` and
`description` frontmatter, plus bundled scripts and data), which several other coding
agents also read. It is verified in Claude Code; it has not been tested in other agents.

- **Agents with skill support:** copy the `renameforce/` folder into that agent's skills
  directory. Check the agent's own documentation for where that is and how skills are
  enabled.
- **Agents without skill support:** add a line to the agent's instructions file (for
  example `AGENTS.md`) telling it to read `renameforce/SKILL.md` and follow it when
  checking Salesforce product names.
- **What the agent needs:** the ability to read files and, for full precision, to run
  `python` or `python3` (3.9 or later). Without script execution it falls back to the
  reduced-precision, chat-only mode.
- **Google Drive:** the Drive section describes tools by function, so it applies to any
  agent with a Drive connector. Most connectors cannot edit document text, so the skill
  produces find-and-replace lists instead.

If it works, or breaks, in another agent, please open an issue.

## Requirements

Python 3.9 or later is recommended, not required. With it, the skill runs deterministic
helper scripts. Without it, the skill falls back to a reduced-precision, chat-only mode
that matches names using the bundled `names-index.json` and tells you so. The scripts use
only the Python standard library; there is nothing to install.

## Using it

Just ask:

- "Check README.md for outdated Salesforce product names."
- "Is 'Tableau CRM' still current?"
- "Update the product names in docs/ and show me each change first."
- "Report only: scan this deck's text for old Salesforce names."

### Modes

| Mode | What happens | Say |
|---|---|---|
| `report` | Lists outdated names and locations. Changes nothing. | "just check", "don't change anything" |
| `review` (default) | Shows each proposed change; applies only what you approve. | nothing needed |
| `apply` | Applies every change it judges safe, then summarizes. | "fix them all" |

To change your default, add one line to your `CLAUDE.md`, `AGENTS.md`, or other project instructions, for
example: `RenameForce skill: default to report mode`.

### Google Drive

If your agent has a Google Drive connector, it can read Google Docs, Slides, and Sheets.
Connectors generally cannot edit a document's text, so the skill gives you grouped
find-and-replace lists (for example "Pardot" to "Marketing Cloud Account Engagement", 7 occurrences) to run
through Docs or Slides Find and Replace (Ctrl+H), which keeps all your formatting.

## How the data stays fresh

Every run reports which data it used, for example "as of 2026-10-10 (cache)".

1. A copy of the data ships with the skill, so it always works offline.
2. A local cache is reused for 7 days.
3. After that, it makes a conditional request (ETag), so an unchanged file costs almost
   nothing, and tries jsDelivr before renameforce.com.

Say "refresh the data" to force a check now.

## What's in this repo

```
renameforce/
  SKILL.md                      the skill
  scripts/get_data.py           data cache and fetch
  scripts/scan.py               finds and classifies mentions
  scripts/build_index.py        builds the compact names index
  references/matching-rules.md  classification and judgment rules
  data/renameforce-data.json    bundled snapshot (synced automatically)
  data/names-index.json         compact lookup (synced automatically)
  data/ambiguous-names.json     generic words never auto-changed
tests/                          python -m unittest discover -s tests
```

The data files are synced from the Renameforce site repository by a GitHub Action. Do not
edit them by hand here.

## Contributing

There are two kinds of contribution, and they go to different places.

### Changes to the skill: open a pull request

Anything about how the skill behaves is handled here by pull request, including
`SKILL.md`, the scripts in `renameforce/scripts/`, `references/`, the tests, the README,
and `renameforce/data/ambiguous-names.json` (the curated list of generic words and
acronyms that are never auto-changed).

1. Fork the repo and make your change on a branch.
2. Add or update a test for any behavior change, and run `python -m unittest discover -s tests -v`.
3. Open a pull request describing what changed and why. For a false positive or missed
   name, include a short example of the text.

The maintainer reviews every pull request and decides what is accepted.

### Changes to product names or rename history: use the form on renameforce.com

Missing renames, wrong dates, and new aliases belong in the Renameforce data, not in this
repo. Please [submit them through the form on renameforce.com](https://renameforce.com/#submit).
Suggestions are verified before they are added, and approved changes reach this skill
automatically through the data sync.

Pull requests that edit `renameforce/data/renameforce-data.json` or `names-index.json`
cannot be accepted: those files are overwritten by the sync.

## Development

```bash
python -m unittest discover -s tests -v
```

## Licenses

- Code: [MIT](LICENSE)
- Data (`renameforce/data/*`): [CC BY 4.0](LICENSE-DATA.md). Attribution: Renameforce (renameforce.com)
