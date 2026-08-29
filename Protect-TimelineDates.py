"""Keep Timeline date dashes aligned after NCMS overwrites article PHP."""
import re
import sys
from pathlib import Path

LEADING_DATE_IN_LIST = re.compile(
    r"(<li><div>)(?:&nbsp;|\xa0|\s)*"
    r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})"
    r"\s*(?:—|&mdash;|–|&ndash;|-)\s*"
)


def protect_timeline_dates(text):
    return LEADING_DATE_IN_LIST.sub(
        r"\1<span class='date'>\2</span> — ",
        text,
    )


def main(argv):
    for raw in argv[1:]:
        path = Path(raw)
        text = path.read_text(encoding="utf-8")
        updated = protect_timeline_dates(text)
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main(sys.argv)
