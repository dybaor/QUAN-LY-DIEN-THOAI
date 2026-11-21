#!/bin/bash
# ==============================================================================
#  OGK - Người Bạn Đồng Hành: launcher duy nhất cho macOS
#    ./Start_App.command                 Bật máy chủ, mở Dashboard + Cổng học tập
#    ./Start_App.command --server-only   Chỉ bật máy chủ
#    ./Start_App.command --reset         Xóa dữ liệu, đưa hệ thống về trạng thái chưa có tài khoản
#  Agent và DNS Proxy chỉ chạy trên Windows. Nhấn Ctrl+C để dừng máy chủ.
# ==============================================================================
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
URL="http://127.0.0.1:8000"
OPEN_BROWSER=1
RESET=0
for arg in "$@"; do
    case "$arg" in
        --server-only) OPEN_BROWSER=0 ;;
        --reset) RESET=1 ;;
        --help) sed -n '2,8p' "$0"; exit 0 ;;
    esac
done

pause_and_exit() {
    read -r -p "Nhấn Enter để đóng..." _ || true
    exit 1
}

if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN=""
    for candidate in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN="$(command -v "$candidate")"
            break
        fi
    done
    if [ -z "$PYTHON_BIN" ]; then
        echo "Không tìm thấy Python 3. Hãy cài Python 3.11+."
        pause_and_exit
    fi
    echo "Đang tạo môi trường Python .venv..."
    "$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
fi
PYTHON="$ROOT_DIR/.venv/bin/python"

if ! "$PYTHON" -c "import fastapi, uvicorn, sqlalchemy, jose, jinja2, argon2, cryptography, websockets" >/dev/null 2>&1; then
    echo "Đang cài thư viện máy chủ..."
    "$PYTHON" -m pip install --disable-pip-version-check -q -r "$ROOT_DIR/server/requirements.txt" || pause_and_exit
fi

if curl -fs --max-time 1 "$URL/health" 2>/dev/null | grep -q "OGK-Server"; then
    if [ "$RESET" -eq 1 ]; then
        echo "Máy chủ đang chạy. Hãy dừng máy chủ trước khi reset dữ liệu."
        pause_and_exit
    fi
    echo "Máy chủ OGK đã chạy sẵn."
    [ "$OPEN_BROWSER" -eq 1 ] && open "$URL/" && open "$URL/child"
    exit 0
fi

if [ "$RESET" -eq 1 ]; then
    "$PYTHON" "$ROOT_DIR/reset_database.py" || pause_and_exit
fi

SERVER_LOG="$ROOT_DIR/.ogk_server.log"
"$PYTHON" "$ROOT_DIR/server/run_server.py" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" >/dev/null 2>&1 || true' EXIT INT TERM

echo "Đang khởi động máy chủ OGK..."
READY=0
for _ in $(seq 1 45); do
    if curl -fs --max-time 1 "$URL/health" 2>/dev/null | grep -q "OGK-Server"; then
        READY=1
        break
    fi
    sleep 1
done
if [ "$READY" -ne 1 ]; then
    echo "Máy chủ không khởi động được. Log:"
    tail -n 30 "$SERVER_LOG"
    pause_and_exit
fi

echo "Đã sẵn sàng tại $URL"
if [ "$OPEN_BROWSER" -eq 1 ]; then
    open "$URL/"
    open "$URL/child"
fi
echo "Máy chủ đang chạy. Nhấn Ctrl+C để dừng."
wait "$SERVER_PID"
