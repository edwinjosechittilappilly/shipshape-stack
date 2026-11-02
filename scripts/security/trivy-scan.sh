#!/usr/bin/env bash
# Run the same Trivy checks as CI against the working tree and any locally built images.
#
#   fs      dependency vulnerabilities (uv.lock, package-lock.json) + committed secrets
#   config  IaC misconfiguration: Dockerfiles, Kubernetes/Helm, Terraform
#   helm    the Helm chart rendered with every optional feature on (default values hide templates)
#   images  app-backend:local and app-frontend:local, when they exist
#
# Policy (severity, unfixed, skip dirs, ignore file) lives in trivy.yaml and .trivyignore.
# Exit code: 0 clean, 1 findings, 2 usage/tool error.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${REPORT_DIR:-$ROOT_DIR/reports/security}"
IMAGES=("${BACKEND_IMAGE:-app-backend:local}" "${FRONTEND_IMAGE:-app-frontend:local}")
SCAN_IMAGES=1

usage() {
  cat <<'EOF'
Usage: scripts/security/trivy-scan.sh [options]

Options:
  --skip-images   do not scan container images
  --out DIR       report directory (default: reports/security; or set REPORT_DIR)
  -h, --help      show this help

Environment:
  BACKEND_IMAGE / FRONTEND_IMAGE   images to scan [app-backend:local / app-frontend:local];
                                   missing images are skipped with a notice (run `make build`)

Reports written to the report directory:
  trivy-<scan>.json   raw results        trivy-<scan>.sarif   code-scanning format
  summary.md          Markdown summary (also appended to $GITHUB_STEP_SUMMARY when set)

Exit code: 0 clean, 1 findings, 2 usage/tool error.
Requires: trivy (https://trivy.dev), python3. Image scans need docker.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-images) SCAN_IMAGES=0 ;;
    --out) OUT_DIR="${2:?--out needs a directory}"; shift ;;
    -h | --help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

info() { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
for tool in trivy python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing required tool: $tool" >&2; exit 2; }
done

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/trivy-*.json "$OUT_DIR"/trivy-*.sarif "$OUT_DIR"/summary.md
cd "$ROOT_DIR"

# Scan once to JSON (exit code ignored here), then convert to SARIF and a readable table.
# The pass/fail decision is made once, over every report, by summarize.py.
emit() {
  local name="$1"
  local json="$OUT_DIR/trivy-${name}.json"
  trivy convert --format sarif --output "$OUT_DIR/trivy-${name}.sarif" "$json"
  trivy convert --format table "$json"
}

info "fs: vulnerabilities + secrets"
trivy fs --scanners vuln,secret --format json --output "$OUT_DIR/trivy-fs.json" .
emit fs

info "config: Dockerfiles, Kubernetes/Helm, Terraform"
trivy config --format json --output "$OUT_DIR/trivy-config.json" .
emit config

if [[ -d deploy/helm/app ]]; then
  info "helm: chart rendered with all optional features enabled"
  trivy config --format json --output "$OUT_DIR/trivy-helm.json" \
    --helm-set "ingress.enabled=true,ingress.host=app.example.com,networkPolicy.enabled=true,backend.autoscaling.enabled=true,frontend.autoscaling.enabled=true" \
    deploy/helm/app
  emit helm
fi

if [[ "$SCAN_IMAGES" == "1" ]]; then
  for image in "${IMAGES[@]}"; do
    name="image-$(basename "${image%%:*}")"
    if command -v docker >/dev/null 2>&1 && docker image inspect "$image" >/dev/null 2>&1; then
      info "image: ${image}"
      trivy image --format json --output "$OUT_DIR/trivy-${name}.json" "$image"
      emit "$name"
    else
      info "image: ${image} not found locally, skipping (run 'make build')"
    fi
  done
fi

info "summary"
rc=0
python3 "$ROOT_DIR/scripts/security/summarize.py" --out "$OUT_DIR/summary.md" "$OUT_DIR"/trivy-*.json || rc=$?
cat "$OUT_DIR/summary.md" 2>/dev/null || true
if [[ -n "${GITHUB_STEP_SUMMARY:-}" && -f "$OUT_DIR/summary.md" ]]; then
  cat "$OUT_DIR/summary.md" >>"$GITHUB_STEP_SUMMARY"
fi

if [[ $rc -eq 0 ]]; then
  info "no HIGH/CRITICAL findings. Reports: ${OUT_DIR}"
else
  info "findings present (exit ${rc}). Reports: ${OUT_DIR}"
fi
exit "$rc"
