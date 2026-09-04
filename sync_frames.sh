#!/usr/bin/env bash
# Push evidence frames to the public bucket the app serves from.
set -euo pipefail
cd "$(dirname "$0")"
gcloud storage rsync --recursive --project mealstogo-76a00 data/frames gs://scripty-frames "$@"
echo "synced → https://storage.googleapis.com/scripty-frames/"
