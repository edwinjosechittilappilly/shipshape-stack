#!/usr/bin/env bash
# End-to-end check on a real (local) Kubernetes cluster:
#   build images -> kind cluster -> dev Postgres -> helm install (migration hook Job) ->
#   smoke test through the frontend proxy -> helm test -> teardown.
#
# Run `scripts/kind-e2e.sh --help` for options. Used by `make kind-e2e` and the opt-in CI job.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CLUSTER_NAME="${CLUSTER_NAME:-app-e2e}"
NAMESPACE="${NAMESPACE:-app}"
RELEASE="${RELEASE:-app}"
BACKEND_IMAGE="${BACKEND_IMAGE:-app-backend:local}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-app-frontend:local}"
LOCAL_PORT="${LOCAL_PORT:-18080}"
HELM_TIMEOUT="${HELM_TIMEOUT:-5m}"
SKIP_BUILD="${SKIP_BUILD:-0}"
KEEP_CLUSTER="${KEEP_CLUSTER:-0}"
# A dedicated kubeconfig: `kind create cluster` would otherwise rewrite the current-context of the
# developer's ~/.kube/config, and every command below must only ever talk to the kind cluster.
KUBECONFIG="${KIND_KUBECONFIG:-${TMPDIR:-/tmp}/kind-${CLUSTER_NAME}.kubeconfig}"
export KUBECONFIG

usage() {
  cat <<EOF
Usage: scripts/kind-e2e.sh [-h|--help]

Environment (defaults in brackets):
  CLUSTER_NAME     kind cluster name [app-e2e]
  NAMESPACE        namespace for the release and dev Postgres [app]
  RELEASE          Helm release name [app]
  BACKEND_IMAGE    backend image tag to build and load [app-backend:local]
  FRONTEND_IMAGE   frontend image tag to build and load [app-frontend:local]
  LOCAL_PORT       local port for the port-forward [18080]
  HELM_TIMEOUT     --timeout for helm install/upgrade [5m]
  SKIP_BUILD=1     reuse existing local images instead of building
  KEEP_CLUSTER=1   do not tear anything down (inspect afterwards with
                   KUBECONFIG=\$KIND_KUBECONFIG kubectl ...)
  KIND_KUBECONFIG  kubeconfig file to use [\${TMPDIR:-/tmp}/kind-<cluster>.kubeconfig]

Teardown deletes the cluster only if this run created it; a pre-existing cluster just loses
the namespace. Requires: docker, kind, kubectl, helm, curl, python3.
EOF
}

case "${1:-}" in
  -h | --help) usage; exit 0 ;;
  "") ;;
  *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
esac

info() { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

for tool in docker kind kubectl helm curl python3; do
  command -v "$tool" >/dev/null 2>&1 || fail "missing required tool: $tool"
done

CONTEXT="kind-${CLUSTER_NAME}"
kc() { kubectl --context "$CONTEXT" "$@"; }
hm() { helm --kube-context "$CONTEXT" "$@"; }

CREATED_CLUSTER=0
NAMESPACE_TOUCHED=0
PF_PID=""

diagnostics() {
  info "Diagnostics (namespace ${NAMESPACE})"
  kind get clusters 2>&1 | sed 's/^/clusters: /' || true
  kc get nodes -o wide || true
  kc -n "$NAMESPACE" get all,pdb,secret,configmap -o wide || true
  hm -n "$NAMESPACE" status "$RELEASE" || true
  hm -n "$NAMESPACE" history "$RELEASE" || true
  kc -n "$NAMESPACE" get events --sort-by=.lastTimestamp || true
  kc -n "$NAMESPACE" describe pods || true
  local pod
  for pod in $(kc -n "$NAMESPACE" get pods -o name 2>/dev/null); do
    echo "--- logs ${pod}"
    kc -n "$NAMESPACE" logs "$pod" --all-containers --tail=200 || true
    kc -n "$NAMESPACE" logs "$pod" --all-containers --previous --tail=100 2>/dev/null || true
  done
}

cleanup() {
  local rc=$?
  trap - EXIT
  [[ -n "$PF_PID" ]] && kill "$PF_PID" 2>/dev/null || true
  if [[ $rc -ne 0 ]]; then
    info "FAILED (exit ${rc})"
    if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
      diagnostics 2>&1 || true
    fi
  fi
  if [[ "$KEEP_CLUSTER" == "1" ]]; then
    info "KEEP_CLUSTER=1: leaving everything in place. Inspect with: KUBECONFIG=${KUBECONFIG} kubectl --context ${CONTEXT} -n ${NAMESPACE} get pods"
  elif [[ "$CREATED_CLUSTER" == "1" ]]; then
    info "Deleting kind cluster ${CLUSTER_NAME}"
    kind delete cluster --name "$CLUSTER_NAME" || true
    rm -f "$KUBECONFIG"
  elif [[ "$NAMESPACE_TOUCHED" == "1" ]]; then
    info "Reused cluster ${CLUSTER_NAME} is kept; deleting namespace ${NAMESPACE}"
    kc delete namespace "$NAMESPACE" --wait=false || true
  fi
  exit "$rc"
}
trap cleanup EXIT

# ---------------------------------------------------------------- images
if [[ "$SKIP_BUILD" == "1" ]]; then
  info "SKIP_BUILD=1: reusing local images"
  docker image inspect "$BACKEND_IMAGE" "$FRONTEND_IMAGE" >/dev/null 2>&1 \
    || fail "SKIP_BUILD=1 but ${BACKEND_IMAGE} / ${FRONTEND_IMAGE} are not present locally"
else
  info "Building ${BACKEND_IMAGE} and ${FRONTEND_IMAGE}"
  docker build -t "$BACKEND_IMAGE" "$ROOT_DIR/backend"
  docker build -t "$FRONTEND_IMAGE" "$ROOT_DIR/frontend"
fi

# ---------------------------------------------------------------- cluster
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  info "Reusing existing kind cluster ${CLUSTER_NAME}"
  kind export kubeconfig --name "$CLUSTER_NAME"
else
  info "Creating kind cluster ${CLUSTER_NAME}"
  CREATED_CLUSTER=1
  kind create cluster --name "$CLUSTER_NAME" --config "$ROOT_DIR/deploy/kind/kind-config.yaml" --wait 120s
fi

# `kind load docker-image` breaks on some Docker image-store setups (containerd snapshotter);
# an image archive is the portable fallback.
load_image() {
  local image="$1"
  if ! kind load docker-image "$image" --name "$CLUSTER_NAME"; then
    info "kind load docker-image failed for ${image}; retrying via image archive"
    local archive
    archive="$(mktemp "${TMPDIR:-/tmp}/kind-image.XXXXXX")"
    docker save "$image" -o "$archive"
    kind load image-archive "$archive" --name "$CLUSTER_NAME"
    rm -f "$archive"
  fi
}
info "Loading images into the cluster"
load_image "$BACKEND_IMAGE"
load_image "$FRONTEND_IMAGE"

# ---------------------------------------------------------------- dependencies
info "Applying dev-only Postgres"
NAMESPACE_TOUCHED=1
kc create namespace "$NAMESPACE" --dry-run=client -o yaml | kc apply -f -
kc -n "$NAMESPACE" apply -f "$ROOT_DIR/deploy/kind/postgres.yaml"
kc -n "$NAMESPACE" rollout status deployment/postgres --timeout=180s

# ---------------------------------------------------------------- release
backend_repo="${BACKEND_IMAGE%:*}"
backend_tag="${BACKEND_IMAGE##*:}"
frontend_repo="${FRONTEND_IMAGE%:*}"
frontend_tag="${FRONTEND_IMAGE##*:}"

info "helm upgrade --install ${RELEASE} (migration hook Job runs first)"
hm upgrade --install "$RELEASE" "$ROOT_DIR/deploy/helm/app" \
  --namespace "$NAMESPACE" \
  --values "$ROOT_DIR/deploy/kind/values-kind.yaml" \
  --set "backend.image.repository=${backend_repo}" --set "backend.image.tag=${backend_tag}" \
  --set "frontend.image.repository=${frontend_repo}" --set "frontend.image.tag=${frontend_tag}" \
  --wait --wait-for-jobs --timeout "$HELM_TIMEOUT"

# ---------------------------------------------------------------- smoke test
frontend_svc="${RELEASE}-frontend"
info "Port-forwarding svc/${frontend_svc} -> localhost:${LOCAL_PORT}"
kc -n "$NAMESPACE" port-forward "svc/${frontend_svc}" "${LOCAL_PORT}:80" >/dev/null 2>&1 &
PF_PID=$!
base="http://127.0.0.1:${LOCAL_PORT}"

for _ in $(seq 1 30); do
  curl -fsS "${base}/healthz" >/dev/null 2>&1 && break
  kill -0 "$PF_PID" 2>/dev/null || fail "port-forward exited early"
  sleep 1
done

info "GET /healthz"
curl -fsS "${base}/healthz"
echo

title="kind-e2e-$(date +%s)"
info "POST /api/v1/items (via the frontend proxy)"
created="$(curl -fsS -X POST "${base}/api/v1/items" -H 'Content-Type: application/json' -d "{\"title\":\"${title}\"}")"
echo "$created"
item_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$created")"

info "GET /api/v1/items"
listed="$(curl -fsS "${base}/api/v1/items")"
python3 -c '
import json, sys
title, raw = sys.argv[1], sys.stdin.read()
items = json.loads(raw)
assert any(i["title"] == title for i in items), f"{title!r} not in {raw}"
print(f"ok: {len(items)} item(s), created item present")
' "$title" <<<"$listed"

info "DELETE /api/v1/items/${item_id}"
test "$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE "${base}/api/v1/items/${item_id}")" = "204"

info "helm test"
hm -n "$NAMESPACE" test "$RELEASE" --logs --timeout 2m

info "kind e2e passed"
