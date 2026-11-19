#!/bin/bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "========================================"
echo "  OGK - Khoi dong Backend + Frontend"
echo "========================================"

if [ ! -d "$ROOT_DIR/.venv" ]; then
    PYTHON_BIN=""
    for candidate in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN="$(command -v "$candidate")"
            break
        fi
    done

    if [ -z "$PYTHON_BIN" ]; then
        echo "Khong tim thay Python 3. Hay cai dat Python 3.11+."
        read -r -p "Nhan Enter de dong..."
        exit 1
    fi

    echo "Dang tao moi truong Python..."
    "$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
fi

PYTHON="$ROOT_DIR/.venv/bin/python"

"$PYTHON" -c "import fastapi, uvicorn, sqlalchemy, jose" >/dev/null 2>&1 || {
    echo "Dang cai dat cac thu vien Backend..."
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install \
        "fastapi>=0.100.0" \
        "uvicorn[standard]>=0.23.0" \
        "sqlalchemy>=2.0.0" \
        "pydantic>=2.0.0" \
        "passlib[argon2]>=1.7.4" \
        "python-jose[cryptography]>=3.3.0" \
        "python-multipart>=0.0.6" \
        "jinja2>=3.1.0" \
        "requests>=2.28.0" \
        "websockets>=11.0"
}

SERVER_LOG="$ROOT_DIR/.ogk_server.log"
"$PYTHON" "$ROOT_DIR/server/run_server.py" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

cleanup() {
    kill "$SERVER_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "Dang khoi dong may chu..."
READY=0
for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:8000/" >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "Server khong khoi dong thanh cong. Log:"
    tail -n 30 "$SERVER_LOG"
    read -r -p "Nhan Enter de dong..."
    exit 1
fi

echo "Da san sang tai http://127.0.0.1:8000"
open "http://127.0.0.1:8000/"
open "http://127.0.0.1:8000/child"

echo "Backend dang chay. De dung ung dung, bam Ctrl+C."
wait "$SERVER_PID"
