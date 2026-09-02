#!/usr/bin/env bash
# Tests, coverage and the SonarQube scan, in the order they have to run.
#
# The coverage report needs one correction before the scanner sees it. coverage
# writes the absolute path of the machine that produced it, and the scanner runs
# in a container where the repository is mounted somewhere else, so every path
# misses and the project reports zero coverage while the tests plainly ran.
# Rewriting the source element to a path relative to the repository root is what
# makes the two agree.
#
# Usage: scripts/scan.sh
# Requires SONAR_TOKEN in .env and a SonarQube reachable at SONAR_HOST_URL.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

SONAR_HOST_URL="${SONAR_HOST_URL:-http://localhost:9000}"
if [ -z "${SONAR_TOKEN:-}" ] && [ -f .env ]; then
  SONAR_TOKEN="$(grep '^SONAR_TOKEN=' .env | cut -d= -f2-)"
fi
: "${SONAR_TOKEN:?Set SONAR_TOKEN, or put it in .env}"

echo "Running the tests with coverage"
(cd apps/api && .venv/bin/python -m pytest -q --cov=app --cov-report=xml)

echo "Rewriting the coverage source path so the scanner can resolve it"
python3 - <<'PYTHON'
import pathlib
import re

report = pathlib.Path("apps/api/coverage.xml")
text = report.read_text(encoding="utf-8")
text = re.sub(
    r"<source>.*?</source>",
    "<source>apps/api/app</source>",
    text,
    count=1,
    flags=re.DOTALL,
)
report.write_text(text, encoding="utf-8")
print("coverage source set to apps/api/app")
PYTHON

echo "Scanning"
docker run --rm --network host \
  -v "${ROOT}:/usr/src" \
  -e SONAR_HOST_URL="${SONAR_HOST_URL}" \
  -e SONAR_TOKEN="${SONAR_TOKEN}" \
  sonarsource/sonar-scanner-cli

echo
echo "Waiting for the server to finish processing"
sleep 20
curl -s -u "${SONAR_TOKEN}:" \
  "${SONAR_HOST_URL}/api/measures/component?component=dsn-lai&metricKeys=bugs,vulnerabilities,code_smells,security_hotspots,coverage,duplicated_lines_density,reliability_rating,security_rating,sqale_rating" \
  | python3 -c "
import json
import sys

names = {'1.0': 'A', '2.0': 'B', '3.0': 'C', '4.0': 'D', '5.0': 'E'}
for measure in sorted(json.load(sys.stdin)['component']['measures'], key=lambda m: m['metric']):
    value = measure.get('value', '')
    if measure['metric'].endswith('_rating'):
        value = names.get(value, value)
    print(measure['metric'].ljust(26), value)
"
