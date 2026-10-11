# Matching rules

How `scripts/scan.py` classifies a mention, and how to judge what it cannot.

## Matching

- Case-insensitive, whole-word, longest name first. "Marketing Cloud Account Engagement"
  is one finding, not two.
- Possessives match ("Pardot's roadmap"); the apostrophe is not part of the match.
- Every historical name and alias in the data is indexed. Names not in the data are ignored.
- Skipped by default: fenced code, inline code, URLs, and file paths. `--include-code`
  scans them too.

## Classification

| Class | When | Notes |
|---|---|---|
| `current` | The text uses the product's present `current_name`, or an alias that is not a past name | An alias gets a `reason` like "alias of CRM Analytics". |
| `outdated` | The text uses a past name that ended, or a legacy alias (an abbreviation or nickname from an earlier name) | `changed_on` is `YYYY` or `YYYY-MM`; empty for a legacy alias. |
| `ambiguous` | The name belongs to more than one product, is current for one product but past for another, or is listed in `data/ambiguous-names.json` | Never auto-changed. |

A name that was reused or reverted (for example a product that returned to an earlier
name) is `current` whenever it equals the present name. Only the in-between names are
`outdated`.

## Legacy aliases

A product's data has two alias lists. `aliases` are current short names (MCE for Marketing
Cloud Engagement) and are `current`. `legacy_aliases` are abbreviations or nicknames that
come from earlier names (SFMC, from Salesforce Marketing Cloud) and are `outdated`: suggest
the product's current name, and its current abbreviation if the user wrote an abbreviation
and `aliases` has one. There is no date for a legacy alias, so **Since** is `—`. The lists
are curated by the data owner, so an abbreviation that is in neither list is not recognized.

## `data/ambiguous-names.json`

A curated list in this repo, not part of the synced data. It holds generic words and
acronym collisions that would produce false flags, such as "Chat", "Flow", "Wave", or
"MCP". Add a name when real content shows a false positive; names are matched
case-insensitively. Keep it short: a name here is never auto-corrected.

## Judgment the script cannot make

| Situation | What to do |
|---|---|
| Past tense, a dated event, or a document older than `changed_on` | Historical. Flag, do not change. |
| A document that mixes old and new names for one product | Treat each old-name use as outdated (unless historical) and point out the inconsistency in the summary. |
| Name inside a quotation, citation, or release-note title | Report, do not edit. |
| Name used as an ordinary word ("let's chat", "data flow") | Not a product mention. Ignore. |
| Acronym that also means something else (MCP, EDA) | Ask, unless context makes it clear. |
| Product name inside a longer proper noun (a partner's product, a customer's brand) | Leave alone. |

## Writing the replacement

- Use the exact `current_name` from the finding.
- Fix the article to match the new name: "an Einstein Analytics dashboard" becomes
  "a CRM Analytics dashboard".
- Keep possessives and plural forms that surround the name.
- Mirror the surrounding capitalization style (title case in headings, sentence case in prose),
  except where the product name has its own casing.
- If the old name appears with the new one ("Pardot, now Marketing Cloud Account Engagement"), the sentence
  is already explaining the rename. Flag it instead of rewriting.
