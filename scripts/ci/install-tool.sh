#!/usr/bin/env bash
# Install a pinned, checksum-verified CLI release binary on a Linux x86_64 GitHub runner.
#
#   scripts/ci/install-tool.sh trivy gitleaks actionlint kubeconform
#
# Why this exists instead of a third-party "setup-X" action per tool:
#   * The SHA-256 below is committed to this repository, so a moved or re-published release tag (the way a
#     compromised release is usually delivered) fails the build instead of running attacker code with our token.
#   * One place to bump versions; every workflow calls the same script (see docs/security.md, "Supply chain").
#
# To bump a tool: change VERSION, download the project's published checksums file for that release, copy the
# linux amd64 line into SHA256, and open a normal PR. Review the upstream release notes first.
#
# Installs into $INSTALL_DIR (default $HOME/.local/bin) and, inside GitHub Actions, adds it to $GITHUB_PATH.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"

if [[ "$(uname -s)-$(uname -m)" != "Linux-x86_64" ]]; then
  echo "install-tool.sh only supports Linux x86_64 runners (got $(uname -s)-$(uname -m))." >&2
  echo "Locally, install the tool with your package manager instead." >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  echo "usage: $0 <trivy|gitleaks|actionlint|kubeconform>..." >&2
  exit 2
fi

mkdir -p "$INSTALL_DIR"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

install_tool() {
  local tool="$1" version url sha256 binary_in_archive
  case "$tool" in
    trivy)
      version="0.76.1"
      url="https://github.com/aquasecurity/trivy/releases/download/v${version}/trivy_${version}_Linux-64bit.tar.gz"
      sha256="c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0"
      binary_in_archive="trivy"
      ;;
    gitleaks)
      version="8.30.1"
      url="https://github.com/gitleaks/gitleaks/releases/download/v${version}/gitleaks_${version}_linux_x64.tar.gz"
      sha256="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
      binary_in_archive="gitleaks"
      ;;
    actionlint)
      version="1.7.12"
      url="https://github.com/rhysd/actionlint/releases/download/v${version}/actionlint_${version}_linux_amd64.tar.gz"
      sha256="8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
      binary_in_archive="actionlint"
      ;;
    kubeconform)
      version="0.8.0"
      url="https://github.com/yannh/kubeconform/releases/download/v${version}/kubeconform-linux-amd64.tar.gz"
      sha256="9bc2bffbf71f261128533edaf912153948b7ff238f9a531ae6d34466ec287883"
      binary_in_archive="kubeconform"
      ;;
    *)
      echo "unknown tool: $tool" >&2
      exit 2
      ;;
  esac

  local archive="$workdir/$tool.tar.gz"
  echo "Installing $tool $version"
  curl --fail --silent --show-error --location --retry 3 --output "$archive" "$url"
  echo "$sha256  $archive" | sha256sum --check --status || {
    echo "Checksum mismatch for $tool $version: refusing to install." >&2
    echo "  expected: $sha256" >&2
    echo "  actual:   $(sha256sum "$archive" | cut -d' ' -f1)" >&2
    exit 1
  }
  mkdir -p "$workdir/$tool"
  tar --extract --gzip --file "$archive" --directory "$workdir/$tool" "$binary_in_archive"
  install -m 0755 "$workdir/$tool/$binary_in_archive" "$INSTALL_DIR/$tool"
}

for tool in "$@"; do
  install_tool "$tool"
done

if [[ -n "${GITHUB_PATH:-}" ]]; then
  echo "$INSTALL_DIR" >>"$GITHUB_PATH"
fi
