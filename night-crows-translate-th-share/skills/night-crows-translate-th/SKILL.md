---
name: night-crows-translate-th
description: Translate Night Crows project content from English to Thai with local glossary enforcement, structure preservation, tag cleanup, and Buddhist Era year conversion. Use when working on Night Crows announcements, shop or item text, UI strings, event notices, patch notes, support replies, spreadsheet snippets, or other project copy that must keep exact line breaks, bullets, numbering, symbols, and protected proper nouns.
---

# Night Crows Thai Translation

Apply this skill whenever a Night Crows translation request needs the approved glossary and strict output formatting.

## Workflow

1. Resolve glossary terms locally before translating.
   - Run `python3 ~/.codex/skills/night-crows-translate-th/scripts/find_glossary_terms.py --file <path>` for source files.
   - Or pipe ad hoc text to the same script with stdin.
   - The script searches in this order: `NIGHTCROWS_GLOSSARY_PATH`, `NCGlosarry01.json` in the current directory or its parents, then the bundled copy in `assets/`.
   - If the script prints `CONFLICT`, every listed Thai variant already exists in the glossary. Pick the variant that matches the surrounding game context. Do not invent a new translation.
   - Use `--term "<english term>"` to inspect every glossary row for one ambiguous term.

2. Clean the source before translating.
   - Remove any substring that starts with `:OaiMd`.
   - Remove every `{attrs="..."}`
   - Remove zero-width characters `U+200B`, `U+200C`, and `U+FEFF`.
   - Collapse repeated spaces created by cleanup, but do not change meaningful line breaks, bullets, numbering, or spacing.

3. Translate with strict preservation.
   - Apply glossary translations exactly when a matched term has one approved Thai rendering.
   - Do not translate these proper nouns: `Razer`, `Logitech`, `ASUS`, `WEMADE`, `Night Crows`, `Razer Gold`, `Razer Silver`.
   - Translate all other normal English words to Thai, including labels such as `Product`, `Price`, `Item`, `Quantity`, and `Limited Edition`.
   - Preserve the original structure exactly: line breaks, bullet points, spacing, numbering, and kept symbols.
   - Keep special symbols exactly as written, including `โ‘  โ‘ก โ‘ข โ‘ฃ โ‘ค โ‘ฅ โ‘ฆ โ‘ง โ‘จ โ–ถ ๏ผ โ” โ–  โ€ป`.
   - Never insert zero-width or invisible characters.

4. Convert years.
   - Convert CE or AD years to Thai Buddhist Era numbers by adding `543`.
   - Change only the year number. Example: `2025` becomes `2568`.
   - Do not change unrelated numeric quantities.

5. Validate when the job is long, repetitive, or file-based.
   - Run `python3 ~/.codex/skills/night-crows-translate-th/scripts/validate_translation_output.py --source-file <source> --output-file <candidate>` if you write a candidate translation to disk before replying.
   - The validator checks for a single code block, leftover tags, zero-width characters, protected proper nouns, special symbols, and line-count drift.
   - Treat validator failures as blockers. Treat year warnings as a prompt to recheck Gregorian-year conversion manually.

6. Return the translation.
   - Output the final translation inside one fenced Markdown code block only.
   - Do not add explanations, comments, or extra text outside the code block.

## Batch Files

Use the batch helper for `.txt` and `.csv` files instead of translating a large file in one shot.

1. Prepare a workdir.
   - Run `python3 ~/.codex/skills/night-crows-translate-th/scripts/batch_translate_files.py prepare <input-file> --output-dir <workdir>`.
   - For CSV, pass `--columns title,description,...` when the target columns are known. If omitted, the script auto-detects likely text columns.
   - CSV batch output appends `<column>_th` by default. Pass `--replace-columns` only when the original English columns should be overwritten.
   - The workdir contains `manifest.json`, `translations.jsonl`, and `chunks/chunk-*.jsonl`.

2. Translate chunk files.
   - Fill the `translation` field inside each `chunks/chunk-*.jsonl` record.
   - Preserve per-cell or per-line structure exactly.
   - Use the embedded `glossary_matches` and `row_context` data to resolve ambiguous glossary variants.

3. Merge the finished chunks.
   - Run `python3 ~/.codex/skills/night-crows-translate-th/scripts/batch_translate_files.py merge <workdir> --output <translated-file>`.
   - The merge command validates missing translations, forbidden tags, zero-width characters, proper nouns, special symbols, and line-count drift before writing the output.
   - Pass `--allow-partial` only if untranslated records should fall back to the source text.

4. Review the merged artifact.
   - For `.txt`, inspect the final text file.
   - For `.csv`, confirm the translated columns and spot-check rows with `CONFLICT` glossary matches or heavy `row_context`.

## Guardrails

- If the source already contains Thai, keep approved Thai wording unless it conflicts with the glossary or proper noun rules.
- If a glossary match is clearly generic and the context shows it is ordinary prose rather than a game term, prefer the natural Thai translation instead of forcing an unrelated glossary label.
- If the source layout and natural Thai wording conflict, preserve the source layout.


