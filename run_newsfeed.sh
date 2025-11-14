#!/bin/bash

# running on Raspberry Pi

PROJECT_DIR="/home/pi/newsfeed"

PYTHON="$PROJECT_DIR/.venv/bin/python"

cd "$PROJECT_DIR" || exit 1

$PYTHON -m newsfeed.main

