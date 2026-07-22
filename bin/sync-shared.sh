#!/usr/bin/env bash
#
# Copy backend/_shared into every deployable Python service directory.
#
# Terraform zips each service folder independently, so a sibling folder is
# never importable at runtime. Folders starting with "_" are skipped by its
# discovery glob, which is why _shared can live there as the single source of
# truth and be vendored into each service at build time.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${ROOT}/backend"
SHARED="${BACKEND}/_shared"

if [[ ! -d "${SHARED}" ]]; then
  echo "error: ${SHARED} not found" >&2
  exit 1
fi

synced=0
for service in "${BACKEND}"/*/; do
  name="$(basename "${service}")"
  [[ "${name}" == _* ]] && continue
  [[ -f "${service}/function.py" ]] || continue

  rm -rf "${service:?}/_shared"
  cp -R "${SHARED}" "${service}/_shared"
  find "${service}/_shared" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

  echo "  synced _shared -> backend/${name}"
  synced=$((synced + 1))
done

echo "sync-shared: updated ${synced} service(s)"
