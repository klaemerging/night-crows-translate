#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from pathlib import Path


DEFAULT_GLOSSARY_NAME = "NCGlosarry01.json"
ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\ufeff]")
TAG_RE = re.compile(r":OaiMd\S*|\{attrs=\"[^\"]*\"\}")
SPACE_RE = re.compile(r"[ \t]{2,}")
ASCII_WORD_RE = re.compile(r"[A-Za-z0-9]")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Find matching Night Crows glossary terms in source text."
    )
    parser.add_argument("--file", help="Read source text from a file.")
    parser.add_argument("--text", help="Read source text from an inline argument.")
    parser.add_argument(
        "--glossary",
        help="Path to the glossary JSON. Defaults to workspace discovery, then bundled asset.",
    )
    parser.add_argument(
        "--term",
        help="Inspect one English glossary term and show every Thai variant defined for it.",
    )
    parser.add_argument(
        "--max-matches",
        type=int,
        default=200,
        help="Maximum number of automatic matches to print.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of plain text.",
    )
    return parser.parse_args()


def discover_glossary(explicit_path):
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())

    env_value = os.environ.get("NIGHTCROWS_GLOSSARY_PATH")
    if env_value:
        candidates.append(Path(env_value).expanduser())

    for base in [Path.cwd(), *Path.cwd().parents]:
        candidates.append(base / DEFAULT_GLOSSARY_NAME)

    bundled = Path(__file__).resolve().parents[1] / "assets" / DEFAULT_GLOSSARY_NAME
    candidates.append(bundled)

    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved

    searched = "\n".join(str(path) for path in candidates)
    raise FileNotFoundError(
        f"Could not find {DEFAULT_GLOSSARY_NAME}. Checked:\n{searched}"
    )


def load_entries(glossary_path):
    with glossary_path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Glossary JSON does not contain an 'entries' list.")
    return entries


def clean_source(text):
    text = ZERO_WIDTH_RE.sub("", text)
    text = TAG_RE.sub("", text)
    text = SPACE_RE.sub(" ", text)
    return text


def normalize_space(text):
    return re.sub(r"\s+", " ", text.strip())


def should_auto_match(term):
    if not term or not any(ch.isalnum() for ch in term):
        return False

    compressed = re.sub(r"[\s_-]+", "", term)
    if len(compressed) < 2:
        return False

    if re.search(r"\s", term):
        return True
    if term.isupper():
        return True
    if any(ch.isupper() for ch in term[1:]):
        return True
    if term[:1].isupper():
        return len(compressed) >= 3
    return len(compressed) >= 4


def build_pattern(term):
    chunks = [re.escape(part) for part in re.split(r"\s+", term.strip()) if part]
    pattern = r"\s+".join(chunks)

    if term and ASCII_WORD_RE.match(term[0]):
        pattern = rf"(?<![A-Za-z0-9]){pattern}"
    if term and ASCII_WORD_RE.match(term[-1]):
        pattern = rf"{pattern}(?![A-Za-z0-9])"
    return re.compile(pattern, re.IGNORECASE)


def group_entries(entries):
    grouped = {}
    for entry in entries:
        english = (entry.get("english") or "").strip()
        thai = (entry.get("thai") or "").strip()
        if not english or not thai:
            continue

        group = grouped.setdefault(
            english,
            {"english": english, "variants": [], "entries": []},
        )
        group["entries"].append(
            {
                "id": entry.get("id"),
                "english": english,
                "thai": thai,
                "korean": entry.get("korean"),
                "languages_present": entry.get("languages_present"),
            }
        )
        if thai not in [variant["thai"] for variant in group["variants"]]:
            group["variants"].append({"thai": thai, "id": entry.get("id")})
    return grouped


def find_matches(grouped, source_text, max_matches):
    lowered = source_text.casefold()
    normalized_source = normalize_space(lowered)
    raw_matches = []

    for english, group in grouped.items():
        if not should_auto_match(english):
            continue

        folded_term = english.casefold()
        normalized_term = normalize_space(folded_term)
        if folded_term not in lowered and normalized_term not in normalized_source:
            continue

        spans = [match.span() for match in build_pattern(english).finditer(source_text)]
        if spans:
            variants = [variant["thai"] for variant in group["variants"]]
            raw_matches.append(
                {
                    "english": english,
                    "variants": variants,
                    "conflict": len(variants) > 1,
                    "entry_ids": [entry["id"] for entry in group["entries"]],
                    "spans": spans,
                }
            )

    filtered = []
    for candidate in sorted(
        raw_matches, key=lambda item: (-len(item["english"]), item["english"].lower())
    ):
        uncovered = []
        for span in candidate["spans"]:
            if not any(existing_span[0] <= span[0] and existing_span[1] >= span[1] for existing in filtered for existing_span in existing["spans"]):
                uncovered.append(span)

        if uncovered:
            candidate["spans"] = uncovered
            filtered.append(candidate)

    filtered.sort(key=lambda item: (-len(item["english"]), item["english"].lower()))
    for item in filtered:
        item.pop("spans", None)
    return filtered[:max_matches]


def inspect_term(grouped, term):
    target = normalize_space(term.casefold())
    results = []
    for english, group in grouped.items():
        if normalize_space(english.casefold()) == target:
            results.append(group)
    results.sort(key=lambda item: item["english"].lower())
    return results


def read_source(args):
    if args.text is not None:
        return args.text
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Provide --file, --text, or piped stdin.")


def print_text_result(result):
    if result["mode"] == "inspect":
        print(f"GLOSSARY {result['glossary']}")
        print(f"TERM {result['term']}")
        print(f"MATCHES {len(result['results'])}")
        for group in result["results"]:
            print(f"ENGLISH {group['english']}")
            for entry in group["entries"]:
                print(
                    f"  - id={entry['id']} thai={entry['thai']}"
                )
        return

    print(f"GLOSSARY {result['glossary']}")
    print(f"CLEANED_SOURCE {'yes' if result['cleaned_changed'] else 'no'}")
    print(f"MATCHES {len(result['matches'])}")
    for match in result["matches"]:
        kind = "CONFLICT" if match["conflict"] else "UNIQUE"
        joined = " | ".join(match["variants"])
        print(f"{kind} {match['english']} => {joined}")


def main():
    args = parse_args()
    glossary_path = discover_glossary(args.glossary)
    grouped = group_entries(load_entries(glossary_path))

    if args.term:
        result = {
            "mode": "inspect",
            "glossary": str(glossary_path),
            "term": args.term,
            "results": inspect_term(grouped, args.term),
        }
    else:
        source_text = read_source(args)
        cleaned = clean_source(source_text)
        result = {
            "mode": "match",
            "glossary": str(glossary_path),
            "cleaned_changed": cleaned != source_text,
            "matches": find_matches(grouped, cleaned, args.max_matches),
        }

    if args.json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    print_text_result(result)


if __name__ == "__main__":
    main()

