#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path


ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\ufeff]")
TAG_RE = re.compile(r":OaiMd\S*|\{attrs=\"[^\"]*\"\}")
SPACE_RE = re.compile(r"[ \t]{2,}")
CODE_BLOCK_RE = re.compile(r"\A```[^\n]*\n([\s\S]*?)\n```\s*\Z")
YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2}|2100)(?!\d)")
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
        description="Validate a Night Crows Thai translation against mechanical rules."
    )
    parser.add_argument("--source-file", help="Read the source text from a file.")
    parser.add_argument("--source-text", help="Read the source text from an inline argument.")
    parser.add_argument("--output-file", help="Read the translation output from a file.")
    parser.add_argument("--output-text", help="Read the translation output from an inline argument.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of plain text.",
    )
    return parser.parse_args()


def read_text(file_arg, text_arg, *, required):
    if text_arg is not None:
        return text_arg
    if file_arg:
        return Path(file_arg).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data:
            return data
    if required:
        raise SystemExit("Provide output text with --output-file, --output-text, or piped stdin.")
    return None


def clean_source(text):
    if text is None:
        return None
    text = ZERO_WIDTH_RE.sub("", text)
    text = TAG_RE.sub("", text)
    text = SPACE_RE.sub(" ", text)
    return text


def extract_code_block(text):
    match = CODE_BLOCK_RE.match(text)
    if not match:
        return None
    return match.group(1)


def validate(source_text, output_text):
    issues = []
    warnings = []

    code = extract_code_block(output_text)
    if code is None:
        issues.append("Output must be exactly one fenced Markdown code block with no extra text.")
        code = output_text

    if ZERO_WIDTH_RE.search(code):
        issues.append("Output contains forbidden zero-width characters.")

    if TAG_RE.search(code):
        issues.append("Output still contains :OaiMd tags or {attrs=\"...\"} tags.")

    if YEAR_RE.search(code):
        warnings.append("Output still contains Gregorian-style 4-digit years.")

    if source_text is not None:
        source_clean = clean_source(source_text)
        if len(source_clean.splitlines()) != len(code.splitlines()):
            issues.append("Line count changed after translation.")

        for noun in PROPER_NOUNS:
            if noun in source_clean and noun not in code:
                issues.append(f"Protected proper noun changed or disappeared: {noun}")

        for symbol in SPECIAL_SYMBOLS:
            if source_clean.count(symbol) != code.count(symbol):
                issues.append(f"Special symbol count changed for {symbol}")

    return {"passed": not issues, "issues": issues, "warnings": warnings}


def print_text_result(result):
    print(f"RESULT {'PASS' if result['passed'] else 'FAIL'}")
    print(f"ISSUES {len(result['issues'])}")
    for issue in result["issues"]:
        print(f"ISSUE {issue}")
    print(f"WARNINGS {len(result['warnings'])}")
    for warning in result["warnings"]:
        print(f"WARNING {warning}")


def main():
    args = parse_args()
    source_text = read_text(args.source_file, args.source_text, required=False)
    output_text = read_text(args.output_file, args.output_text, required=True)
    result = validate(source_text, output_text)

    if args.json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    print_text_result(result)


if __name__ == "__main__":
    main()

