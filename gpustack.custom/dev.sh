#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
UI_DIR="$ROOT_DIR/gpustack-ui"

usage() {
    cat <<'EOF'
Usage: dev.sh <target> [options]

Targets:
  ui                Compile frontend only
  server            Build server image + restart
  worker            Build worker image + restart

Options:
  --full            Compile frontend before building image (server only)
  --build           Build image only, don't restart
  --restart         Restart only, don't rebuild image
  --env <name>      Environment: dev (default) or prod
  -h, --help        Show this help

Examples:
  ./dev.sh ui                    # compile frontend
  ./dev.sh server                # build server image + restart
  ./dev.sh server --full         # compile frontend + build + restart
  ./dev.sh server --build        # build image only
  ./dev.sh server --restart      # restart only
  ./dev.sh worker                # build worker image + restart
  ./dev.sh worker --env prod     # build worker with prod env
EOF
    exit 0
}

# ── Parse args ──────────────────────────────────────────────────
[[ $# -eq 0 ]] && usage

TARGET="$1"; shift
DO_UI=false
DO_BUILD=true
DO_RESTART=true
ENV_NAME="dev"

case "$TARGET" in
    ui) DO_UI=true; DO_BUILD=false; DO_RESTART=false ;;
    server|worker) ;;
    help|-h|--help) usage ;;
    *) echo "Unknown target: $TARGET"; usage ;;
esac

while [[ $# -gt 0 ]]; do
    case "$1" in
        --full)    DO_UI=true ;;
        --build)   DO_RESTART=false ;;
        --restart) DO_BUILD=false ;;
        --env)     ENV_NAME="$2"; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
    shift
done

COMPOSE_FILE="$SCRIPT_DIR/docker-compose-${TARGET}.yaml"
ENV_FILE="$SCRIPT_DIR/.env-${TARGET}-${ENV_NAME}"

# ── Validate ────────────────────────────────────────────────────
if [[ "$DO_BUILD" == true || "$DO_RESTART" == true ]]; then
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        echo "ERROR: $COMPOSE_FILE not found"
        exit 1
    fi
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "ERROR: $ENV_FILE not found"
        echo "Available: $(ls "$SCRIPT_DIR"/.env-${TARGET}-* 2>/dev/null | xargs -n1 basename | tr '\n' ' ')"
        exit 1
    fi
fi

DOCKER="docker"
if ! $DOCKER info &>/dev/null; then
    DOCKER="sudo docker"
fi

SECONDS=0

# ── Frontend ────────────────────────────────────────────────────
if [[ "$DO_UI" == true ]]; then
    echo "==> Compiling frontend..."
    (cd "$UI_DIR" && npm run build)
    echo "==> Frontend compiled (${SECONDS}s)"
fi

# ── Docker build ────────────────────────────────────────────────
if [[ "$DO_BUILD" == true ]]; then
    echo "==> Building ${TARGET} image..."
    (cd "$ROOT_DIR" && $DOCKER compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build)
    echo "==> Image built (${SECONDS}s)"
fi

# ── Restart ─────────────────────────────────────────────────────
if [[ "$DO_RESTART" == true ]]; then
    echo "==> Restarting ${TARGET}..."
    (cd "$ROOT_DIR" && $DOCKER compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d)
    echo "==> ${TARGET} restarted (${SECONDS}s)"
fi

echo "==> Done in ${SECONDS}s"
