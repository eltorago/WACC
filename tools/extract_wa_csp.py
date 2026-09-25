"""Extract the WA Government Cyber Security Policy into a corpus JSON file.

Extraction tooling. Not part of the shipped package.

The policy is a designed document rather than a ruled table, so structure comes from
its own numbering. The table of contents supplies the authoritative list of section
numbers and titles, and the body is then split on exactly those headings — which stops
a line that merely begins with a number from being read as a new section.

Requirements sit in the lettered items beneath each heading. Where a section states an
obligation without lettered items, the section itself is the requirement.
"""

import json
import os
import sys

import pdfplumber

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(HERE, "data", "raw", "documents", "wa-cyber-security-policy.pdf")
OUTPUT = os.path.join(HERE, "data", "corpus", "wa-csp.json")

sys.path.insert(0, HERE)
from wacc.policy.wa_parser import page_lines, parse_contents, find_functions, split_sections, build_records


def main() -> int:
    with pdfplumber.open(SOURCE) as pdf:
        lines = page_lines(pdf)
        pages = len(pdf.pages)

    numbers, toc_end = parse_contents(lines)
    sections = split_sections(lines, numbers, toc_end)
    records = build_records(sections)

    found = {s["number"] for s in sections}
    wanted = {n: numbers[n] for n in numbers if "." in n}
    missing = sorted(set(wanted) - found, key=lambda n: [int(p) for p in n.split(".")])
    functions = find_functions(lines, wanted, numbers)

    data = {
        "source_file": os.path.basename(SOURCE),
        "title": "Western Australian Government Cyber Security Policy 2024",
        "page_count": pages,
        "contents_sections": numbers,
        "functions": functions,
        "records": records,
    }
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)

    print("pages              %d" % pages)
    print("numbered sections     %d in contents, %d functions named" % (len(wanted), len(functions)))
    print("sections located     %d" % len(sections))
    print("requirements         %d" % len(records))
    print("not located          %s" % (missing if missing else "none"))
    for record in records[:4]:
        print("\n  %-8s %s" % (record["identifier"], record["section_title"]))
        print("           %s" % str(record["text"])[:100])
    return 0


if __name__ == "__main__":
    sys.exit(main())
