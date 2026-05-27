#!/bin/bash
# Custom entrypoint wrapper — creates a symlink so that the official
# model_scope cache path points to an externally mounted ModelScope cache.
# This avoids patching the official GPUStack source code.

if [ -d "/modelscope-cache" ] && [ ! -e "/var/cache/gpustack/model_scope" ]; then
    mkdir -p /var/cache/gpustack
    ln -sfn /modelscope-cache /var/cache/gpustack/model_scope
fi

exec /usr/bin/entrypoint.sh "$@"
