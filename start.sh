#!/bin/bash
set -e
PYTHON_BIN=/home/eins777/workspace/imoji/.venv/bin/python ./node_modules/.bin/next build
PYTHON_BIN=/home/eins777/workspace/imoji/.venv/bin/python ./node_modules/.bin/next start
