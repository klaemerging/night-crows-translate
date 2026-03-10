#!/usr/bin/env python3

import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path

from find_glossary_terms import (
    clean_source,
    discover_glossary,
    find_matches,
    group_entries,
    load_entries,
)


ASCII_RE = re.compile(r"[A-Za-z]")
ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\ufeff]")
TAG_RE = re.compile(r":OaiMd\S*|\{attrs=\"[^\"]*\"\}")
YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2}|2100)(?!\d)")
SIMPLE_CODE_RE = re.compile(r"[A-Za-z0-9_-]+")
HEADER_HINTS = (
    "text",
    "title",
    "name",
    "desc",
    "description",
    "content",
    "message",
    "body",
    "label",
    "item",
    "product",
    "notice",
    "subject",
)
PROPER_NOUNS = [
    "Razer",
    "Logitech",
    "ASUS",
    "WEMADE",
    "Night Crows",
    "Razer Gold",
    "Razer Silver",
]
SPECIAL_SYMBOLS = ["โ‘ ", "โ‘ก", "โ‘ข", "โ‘ฃ", "โ‘ค", "โ‘ฅ", "โ‘ฆ", "โ‘ง", "โ‘จ", "โ–ถ", "๏ผ", "โ”", "โ– ", "โ€ป"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Prepare and merge batch Night Crows translations for TXT and CSV files."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Create a batch translation workdir.")
    prepare.add_argument("input", help="Path to the input .txt or .csv file.")
    prepare.add_argument("--output-dir", required=True, help="Directory to write the batch workdir.")
    prepare.add_argument(
        "--columns",
        help="Comma-separated CSV columns to translate. If omitted, the script auto-detects likely text columns.",
    )
    prepare.add_argument(
        "--replace-columns",
        action="store_true",
        help="For CSV only, overwrite the source columns instead of creating <column>_th columns.",
    )
    prepare.add_argument(
        "--glossary",
        help="Path to the glossary JSON. Defaults to workspace discovery, then the bundled asset.",
    )
    prepare.add_argument(
        "--max-chars",
        type=int,
        default=5000,
        help="Approximate maximum source characters per chunk file.",
    )
    prepare.add_argument(
        "--max-segments",
        type=int,
        default=100,
        help="Maximum translatable records per chunk file.",
    )
    prepare.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output directory.",
    )

    merge = subparsers.add_parser("merge", help="Merge translated chunk files back into a final file.")
    merge.add_argument("workdir", help="Batch workdir created by the prepare command.")
    merge.add_argument("--output", required=True, help="Path to the translated output file.")
    merge.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow missing translations and fall back to the original source text.",
    )

    return parser.parse_args()


def detect_file_type(path):
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return "txt"
    if suffix == ".csv":
        return "csv"
    raise SystemExit("Only .txt and .csv inputs are supported.")


def ensure_workdir(path, force):
    if path.exists():
        if not force:
            raise SystemExit(f"Output directory already exists: {path}")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    path.mkdir(parents=True, exist_ok=True)
    (path / "chunks").mkdir(parents=True, exist_ok=True)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path):
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                records.append(json.loads(payload))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} at line {line_number}: {exc}") from exc
    return records


def csv_dialect_to_meta(path):
    sample = path.read_text(encoding="utf-8-sig")[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    return {
        "delimiter": getattr(dialect, "delimiter", ","),
        "quotechar": getattr(dialect, "quotechar", '"'),
        "doublequote": getattr(dialect, "doublequote", True),
        "escapechar": getattr(dialect, "escapechar", None),
        "lineterminator": getattr(dialect, "lineterminator", "\n"),
        "quoting": getattr(dialect, "quoting", csv.QUOTE_MINIMAL),
        "skipinitialspace": getattr(dialect, "skipinitialspace", False),
    }


def dialect_from_meta(meta):
    class LoadedDialect(csv.Dialect):
        delimiter = meta["delimiter"]
        quotechar = meta["quotechar"]
        doublequote = meta["doublequote"]
        escapechar = meta["escapechar"]
        lineterminator = meta["lineterminator"]
        quoting = meta["quoting"]
        skipinitialspace = meta["skipinitialspace"]

    return LoadedDialect


def load_csv(path, dialect_meta):
    dialect = dialect_from_meta(dialect_meta)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, dialect=dialect)
        fieldnames = reader.fieldnames or []
        if not fieldnames:
            raise SystemExit("CSV input must contain a header row.")
        rows = []
        for row in reader:
            rows.append({field: row.get(field, "") or "" for field in fieldnames})
    return fieldnames, rows


def detect_csv_columns(fieldnames, rows):
    selected = []
    for field in fieldnames:
        lower = field.casefold()
        if lower.endswith("_th") or "thai" in lower:
            continue

        nonempty = 0
        ascii_cells = 0
        long_cells = 0
        spaced_cells = 0
        code_like_cells = 0

        for row in rows[:200]:
            value = clean_source((row.get(field) or "").strip())
            if not value:
                continue
            nonempty += 1
            if ASCII_RE.search(value):
                ascii_cells += 1
            if len(value) >= 12:
                long_cells += 1
            if " " in value or "\n" in value:
                spaced_cells += 1
            if SIMPLE_CODE_RE.fullmatch(value) and len(value) <= 10 and " " not in value:
                code_like_cells += 1

        if ascii_cells == 0:
            continue

        score = 0
        if any(hint in lower for hint in HEADER_HINTS):
            score += 3
        score += long_cells + spaced_cells + ascii_cells
        score -= code_like_cells

        if nonempty > 0 and score > 0:
            selected.append(field)

    return selected


def split_columns(raw_columns):
    return [part.strip() for part in raw_columns.split(",") if part.strip()]


def build_row_context(row, current_column):
    context = {}
    for key, value in row.items():
        if key == current_column:
            continue
        text = (value or "").strip()
        if not text:
            continue
        if len(text) > 120:
            continue
        context[key] = text
        if len(context) >= 6:
            break
    return context


def make_txt_segments(input_path, grouped_glossary):
    source = input_path.read_text(encoding="utf-8")
    endswith_newline = source.endswith("\n")
    lines = source.splitlines()

    segments = []
    for line_number, line in enumerate(lines, start=1):
        cleaned = clean_source(line)
        needs_translation = bool(cleaned.strip()) and bool(ASCII_RE.search(cleaned))
        segments.append(
            {
                "segment_id": f"txt:{line_number}",
                "kind": "txt_line",
                "line_number": line_number,
                "source": line,
                "cleaned_source": cleaned,
                "needs_translation": needs_translation,
                "translation": "" if needs_translation else line,
                "glossary_matches": find_matches(grouped_glossary, cleaned, 25) if needs_translation else [],
            }
        )

    return {
        "file_type": "txt",
        "segments": segments,
        "meta": {
            "line_count": len(lines),
            "endswith_newline": endswith_newline,
        },
    }


def make_csv_segments(input_path, grouped_glossary, columns, replace_columns):
    dialect_meta = csv_dialect_to_meta(input_path)
    fieldnames, rows = load_csv(input_path, dialect_meta)

    if columns:
        selected_columns = split_columns(columns)
    else:
        selected_columns = detect_csv_columns(fieldnames, rows)

    if not selected_columns:
        raise SystemExit("Could not determine any CSV columns to translate. Pass --columns explicitly.")

    missing = [column for column in selected_columns if column not in fieldnames]
    if missing:
        raise SystemExit(f"CSV columns not found: {', '.join(missing)}")

    target_columns = {
        column: column if replace_columns else f"{column}_th" for column in selected_columns
    }

    segments = []
    for row_index, row in enumerate(rows, start=1):
        for column in selected_columns:
            source = row.get(column, "")
            cleaned = clean_source(source)
            needs_translation = bool(cleaned.strip()) and bool(ASCII_RE.search(cleaned))
            segments.append(
                {
                    "segment_id": f"csv:{row_index}:{column}",
                    "kind": "csv_cell",
                    "row_index": row_index,
                    "column": column,
                    "target_column": target_columns[column],
                    "source": source,
                    "cleaned_source": cleaned,
                    "needs_translation": needs_translation,
                    "translation": "" if needs_translation else source,
                    "row_context": build_row_context(row, column),
                    "glossary_matches": find_matches(grouped_glossary, cleaned, 25) if needs_translation else [],
                }
            )

    return {
        "file_type": "csv",
        "segments": segments,
        "meta": {
            "fieldnames": fieldnames,
            "selected_columns": selected_columns,
            "target_columns": target_columns,
            "dialect": dialect_meta,
            "row_count": len(rows),
            "replace_columns": replace_columns,
        },
    }


def chunk_segments(segments, max_chars, max_segments):
    current = []
    current_chars = 0
    chunks = []

    for segment in [item for item in segments if item["needs_translation"]]:
        segment_chars = max(1, len(segment["cleaned_source"]))
        should_split = bool(current) and (
            len(current) >= max_segments or current_chars + segment_chars > max_chars
        )
        if should_split:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(segment)
        current_chars += segment_chars

    if current:
        chunks.append(current)
    return chunks


def write_chunks(workdir, segments, max_chars, max_segments):
    chunks = chunk_segments(segments, max_chars, max_segments)
    chunk_dir = workdir / "chunks"
    for index, chunk in enumerate(chunks, start=1):
        path = chunk_dir / f"chunk-{index:03d}.jsonl"
        chunk_records = []
        for record in chunk:
            chunk_records.append(
                {
                    key: value
                    for key, value in record.items()
                    if key in {
                        "segment_id",
                        "kind",
                        "line_number",
                        "row_index",
                        "column",
                        "target_column",
                        "source",
                        "cleaned_source",
                        "row_context",
                        "glossary_matches",
                        "translation",
                    }
                }
            )
        write_jsonl(path, chunk_records)
    return len(chunks)


def default_output_name(input_path):
    return f"{input_path.stem}.th{input_path.suffix}"


def command_prepare(args):
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input file not found: {input_path}")

    workdir = Path(args.output_dir).expanduser().resolve()
    ensure_workdir(workdir, args.force)

    glossary_path = discover_glossary(args.glossary)
    grouped_glossary = group_entries(load_entries(glossary_path))
    file_type = detect_file_type(input_path)

    if file_type == "txt":
        prepared = make_txt_segments(input_path, grouped_glossary)
    else:
        prepared = make_csv_segments(
            input_path, grouped_glossary, args.columns, args.replace_columns
        )

    segments = prepared["segments"]
    chunk_count = write_chunks(workdir, segments, args.max_chars, args.max_segments)

    manifest = {
        "version": 1,
        "input_path": str(input_path),
        "file_type": file_type,
        "glossary_path": str(glossary_path),
        "suggested_output": default_output_name(input_path),
        "segment_count": len(segments),
        "translatable_segment_count": sum(1 for segment in segments if segment["needs_translation"]),
        "chunk_count": chunk_count,
        "max_chars": args.max_chars,
        "max_segments": args.max_segments,
        "meta": prepared["meta"],
    }

    write_json(workdir / "manifest.json", manifest)
    write_jsonl(workdir / "translations.jsonl", segments)

    print(f"WORKDIR {workdir}")
    print(f"INPUT {input_path}")
    print(f"FILE_TYPE {file_type}")
    if file_type == "csv":
        print(f"COLUMNS {', '.join(prepared['meta']['selected_columns'])}")
    print(f"SEGMENTS {manifest['segment_count']}")
    print(f"TO_TRANSLATE {manifest['translatable_segment_count']}")
    print(f"CHUNKS {manifest['chunk_count']}")
    print(f"SUGGESTED_OUTPUT {manifest['suggested_output']}")


def load_workdir_records(workdir):
    manifest = read_json(workdir / "manifest.json")
    master_records = read_jsonl(workdir / "translations.jsonl")
    records_by_id = {record["segment_id"]: record for record in master_records}

    for chunk_path in sorted((workdir / "chunks").glob("chunk-*.jsonl")):
        for chunk_record in read_jsonl(chunk_path):
            segment_id = chunk_record.get("segment_id")
            if segment_id not in records_by_id:
                continue
            translation = chunk_record.get("translation", "")
            if translation != "":
                records_by_id[segment_id]["translation"] = translation
                records_by_id[segment_id]["translation_source"] = chunk_path.name

    return manifest, master_records


def append_limited(target, message, limit=50):
    if len(target) < limit:
        target.append(message)


def validate_segment(record, allow_partial, issues, warnings):
    translation = record.get("translation", "")
    source = record.get("source", "")

    if record.get("needs_translation") and translation.strip() == "":
        if allow_partial:
            append_limited(
                warnings,
                f"{record['segment_id']}: missing translation; source text will be copied through.",
            )
            translation = source
        else:
            append_limited(issues, f"{record['segment_id']}: missing translation.")
            return

    if ZERO_WIDTH_RE.search(translation):
        append_limited(issues, f"{record['segment_id']}: contains forbidden zero-width characters.")

    if TAG_RE.search(translation):
        append_limited(issues, f"{record['segment_id']}: contains forbidden tags.")

    if len(source.splitlines()) != len(translation.splitlines()):
        append_limited(issues, f"{record['segment_id']}: line count changed inside the segment.")

    for noun in PROPER_NOUNS:
        if noun in source and noun not in translation:
            append_limited(issues, f"{record['segment_id']}: protected proper noun changed: {noun}")

    for symbol in SPECIAL_SYMBOLS:
        if source.count(symbol) != translation.count(symbol):
            append_limited(issues, f"{record['segment_id']}: special symbol count changed for {symbol}")

    for match in YEAR_RE.finditer(source):
        year = match.group(0)
        if year in translation:
            append_limited(
                warnings,
                f"{record['segment_id']}: Gregorian year {year} still appears in the translation.",
            )


def render_txt_output(manifest, records, allow_partial):
    ordered = sorted(records, key=lambda record: record["line_number"])
    lines = []
    for record in ordered:
        translation = record.get("translation", "")
        if translation == "" and allow_partial:
            translation = record["source"]
        lines.append(translation)

    text = "\n".join(lines)
    if manifest["meta"].get("endswith_newline") and lines:
        text += "\n"
    return text


def build_output_fieldnames(fieldnames, selected_columns, target_columns, replace_columns):
    if replace_columns:
        return fieldnames

    result = []
    selected = set(selected_columns)
    for field in fieldnames:
        result.append(field)
        if field in selected:
            result.append(target_columns[field])
    return result


def render_csv_output(manifest, records, allow_partial):
    input_path = Path(manifest["input_path"])
    fieldnames, rows = load_csv(input_path, manifest["meta"]["dialect"])
    by_id = {record["segment_id"]: record for record in records}

    selected_columns = manifest["meta"]["selected_columns"]
    target_columns = manifest["meta"]["target_columns"]
    replace_columns = manifest["meta"]["replace_columns"]
    output_fieldnames = build_output_fieldnames(
        fieldnames, selected_columns, target_columns, replace_columns
    )

    rendered_rows = []
    for row_index, row in enumerate(rows, start=1):
        output_row = dict(row)
        for column in selected_columns:
            segment = by_id[f"csv:{row_index}:{column}"]
            translation = segment.get("translation", "")
            if translation == "" and allow_partial:
                translation = segment["source"]

            if replace_columns:
                output_row[column] = translation
            else:
                output_row[target_columns[column]] = translation
        rendered_rows.append(output_row)

    return output_fieldnames, rendered_rows


def write_csv_output(path, fieldnames, rows, dialect_meta):
    dialect = dialect_from_meta(dialect_meta)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, dialect=dialect, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def command_merge(args):
    workdir = Path(args.workdir).expanduser().resolve()
    if not workdir.is_dir():
        raise SystemExit(f"Workdir not found: {workdir}")

    manifest, records = load_workdir_records(workdir)

    issues = []
    warnings = []
    for record in records:
        validate_segment(record, args.allow_partial, issues, warnings)

    if issues:
        print(f"RESULT FAIL")
        print(f"ISSUES {len(issues)}")
        for issue in issues:
            print(f"ISSUE {issue}")
        print(f"WARNINGS {len(warnings)}")
        for warning in warnings[:20]:
            print(f"WARNING {warning}")
        raise SystemExit(1)

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if manifest["file_type"] == "txt":
        output_path.write_text(
            render_txt_output(manifest, records, args.allow_partial), encoding="utf-8"
        )
    else:
        fieldnames, rows = render_csv_output(manifest, records, args.allow_partial)
        write_csv_output(output_path, fieldnames, rows, manifest["meta"]["dialect"])

    print("RESULT PASS")
    print(f"OUTPUT {output_path}")
    print(f"SEGMENTS {manifest['segment_count']}")
    print(f"WARNINGS {len(warnings)}")
    for warning in warnings[:20]:
        print(f"WARNING {warning}")


def main():
    args = parse_args()
    if args.command == "prepare":
        command_prepare(args)
        return
    if args.command == "merge":
        command_merge(args)
        return
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()

