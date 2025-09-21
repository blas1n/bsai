#!/bin/bash
# Manual environment loading script
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    echo "Environment variables loaded from .env"
else
    echo ".env file not found"
fi
