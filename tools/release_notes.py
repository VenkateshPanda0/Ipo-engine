"""Print one version's section of CHANGELOG.md (the body of its GitHub Release).

    python tools/release_notes.py 0.4.0            # or v0.4.0

Exits non-zero, printing why, if the section is missing or empty: a release must not go out with
no notes.
"""

import re
import sys
from pathlib import Path


class NoNotes(Exception):
    pass


def extract(changelog: str, version: str) -> str:
    version = version.removeprefix("v")
    sections = re.split(r"^## ", changelog, flags=re.M)
    for sec in sections[1:]:
        head, _, body = sec.partition("\n")
        if re.match(rf"\[{re.escape(version)}\]( |$)", head.strip()):
            body = body.strip()
            if not body:
                raise NoNotes(f"CHANGELOG.md has a heading for {version} but nothing under it")
            return body
    raise NoNotes(f"CHANGELOG.md has no section for {version}")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        print(
            extract((Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(), argv[1])
        )
    except NoNotes as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
