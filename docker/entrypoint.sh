#!/bin/sh
# Start the worker (restarted if it ever exits) and nginx in the foreground.
set -e
cd /app
(
  while true; do
    python3 -m worker || true
    echo "worker stopped, restarting in 10 seconds"
    sleep 10
  done
) &
exec nginx -g 'daemon off;'
