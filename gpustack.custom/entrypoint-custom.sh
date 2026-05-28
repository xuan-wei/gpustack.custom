#!/bin/bash
# Custom entrypoint wrapper — wires external HuggingFace / ModelScope caches
# into the official GPUStack cache layout via symlinks, without patching
# the official source code.
#
# Mount conventions (set in docker-compose):
#   /huggingface-cache   ← host HF cache (e.g. /data/shared/huggingface/hub)
#   /modelscope-cache    ← host ModelScope cache (e.g. /data/shared/modelscope/hub/models)
#
# Each symlink is created only when the target path is absent from the parent
# gpustack-cache mount. If the user has not configured an external cache, the
# defaults point the mount source back inside gpustack-cache; the target then
# already exists via the parent mount and the symlink step is skipped — yielding
# upstream behavior.

mkdir -p /var/cache/gpustack

if [ -d "/huggingface-cache" ] && [ ! -e "/var/cache/gpustack/huggingface" ]; then
    ln -sfn /huggingface-cache /var/cache/gpustack/huggingface
fi

if [ -d "/modelscope-cache" ] && [ ! -e "/var/cache/gpustack/model_scope" ]; then
    ln -sfn /modelscope-cache /var/cache/gpustack/model_scope
fi

exec /usr/bin/entrypoint.sh "$@"
