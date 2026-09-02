"""Rewrite a coverage report so the scanner can resolve its paths.

pytest runs inside apps/api and writes filenames relative to that directory.
The scanner runs in a container with the repository at a different root, so the
two never meet. This rewrites the report to repository-relative paths, which
both sides agree on.
"""

import pathlib
import sys
import xml.etree.ElementTree as ElementTree

PREFIX = "apps/api/app/"


def main(path: str) -> int:
    report = pathlib.Path(path)
    if not report.exists():
        print(f"No coverage report at {report}.")
        return 1

    tree = ElementTree.parse(report)
    root = tree.getroot()

    sources = root.find("sources")
    if sources is not None:
        for source in list(sources):
            sources.remove(source)
        element = ElementTree.SubElement(sources, "source")
        element.text = "."

    rewritten = 0
    for element in root.iter("class"):
        filename = element.get("filename")
        if filename and not filename.startswith(PREFIX):
            element.set("filename", PREFIX + filename)
            rewritten += 1

    tree.write(report, encoding="utf-8", xml_declaration=True)
    print(f"Rewrote {rewritten} paths in {report}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "apps/api/coverage.xml"))
