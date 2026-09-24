#!/usr/bin/env bash
# Deploy exam-chuu to Firebase: sync pipeline output -> build web -> firestore/functions/hosting -> import data.
# Prereqs (see README.md §2): firebase login, .firebaserc project set, functions/venv created,
# web/.env.local + functions/.env filled in, gcloud application-default login (for import_bank.py).
#
# Usage: scripts/deploy.sh [options]
#   --full          also regenerate pipeline output first: python pipeline/run_all.py (slow, needs source PDFs)
#   --minsan        also refresh the min-san bank first: python pipeline/minsan.py build && pipeline/build.py
#                   (run this after adding/solving more min-san chunks; does not re-scrape or re-render)
#   --skip-import   skip scripts/import_bank.py (Firestore exam/answer upload) — hosting/functions only
#   --skip-tests    skip the pytest gate (default: run `pytest tests -q` first, abort deploy on failure)
#   --project ID    firebase project id (default: read from .firebaserc)
#
set -euo pipefail
cd "$(dirname "$0")/.."

FULL=0
MINSAN=0
SKIP_IMPORT=0
SKIP_TESTS=0
PROJECT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full) FULL=1; shift ;;
    --minsan) MINSAN=1; shift ;;
    --skip-import) SKIP_IMPORT=1; shift ;;
    --skip-tests) SKIP_TESTS=1; shift ;;
    --project) PROJECT="$2"; shift 2 ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 1 ;;
  esac
done

if [[ -z "$PROJECT" ]]; then
  PROJECT=$(python -c "import json; print(json.load(open('.firebaserc'))['projects']['default'])" 2>/dev/null || true)
fi
if [[ -z "$PROJECT" ]]; then
  echo "No project set. Pass --project <id> or set .firebaserc / run 'firebase use <id>'." >&2
  exit 1
fi
echo "== exam-chuu deploy -> Firebase project: $PROJECT =="

if [[ "$SKIP_TESTS" == 0 ]]; then
  echo "-- pytest gate --"
  python -m pytest tests -q
fi

if [[ "$FULL" == 1 ]]; then
  echo "-- rebuilding pipeline from source PDFs (slow) --"
  python pipeline/run_all.py
fi

if [[ "$MINSAN" == 1 ]]; then
  echo "-- refreshing min-san bank (merge + rebuild sets) --"
  python pipeline/minsan.py build
  python pipeline/build.py
fi

echo "-- syncing pipeline output into web/public --"
python scripts/sync_assets.py

echo "-- building web (production) --"
(cd web && npm run build)

echo "-- firebase deploy: firestore rules/indexes, functions, hosting --"
firebase deploy --only firestore:rules,firestore:indexes,functions,hosting --project "$PROJECT"

if [[ "$SKIP_IMPORT" == 0 ]]; then
  echo "-- importing exam catalog + answer keys into Firestore --"
  python scripts/import_bank.py --project "$PROJECT"
fi

echo "== deploy complete: https://$PROJECT.web.app =="
