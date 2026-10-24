#!/bin/sh
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || exit 1
fi
# requirements.txt 有變動（例如更新了工作台）就重新安裝套件
if ! cmp -s requirements.txt .venv/requirements.installed; then
  .venv/bin/pip install -r requirements.txt || exit 1
  cp requirements.txt .venv/requirements.installed
fi
exec .venv/bin/python app.py
