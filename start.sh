#!/bin/sh
cd "$(dirname "$0")"
# 預設用專案裡的 .venv；想放在別處就設 NS_VENV（例如沙箱會限制工作區寫入的環境）
VENV="${NS_VENV:-$PWD/.venv}"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV" || exit 1
fi
# requirements.txt 有變動（例如更新了工作台）就重新安裝套件
if ! cmp -s requirements.txt "$VENV/requirements.installed"; then
  "$VENV/bin/pip" install -r requirements.txt || exit 1
  cp requirements.txt "$VENV/requirements.installed"
fi
exec "$VENV/bin/python" app.py
