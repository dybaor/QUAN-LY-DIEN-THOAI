import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = BASE_DIR / "server"
AGENT_DIR = BASE_DIR / "agent"

for p in [str(SERVER_DIR), str(AGENT_DIR), str(BASE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Alias sys.modules so app and server.app are strictly identical singletons
import app  # type: ignore
sys.modules['server.app'] = app
import app.database  # type: ignore
sys.modules['server.app.database'] = app.database
import app.models  # type: ignore
sys.modules['server.app.models'] = app.models
import app.websocket_manager  # type: ignore
sys.modules['server.app.websocket_manager'] = app.websocket_manager
import app.routers  # type: ignore
sys.modules['server.app.routers'] = app.routers
import app.routers.policy_events  # type: ignore
sys.modules['server.app.routers.policy_events'] = app.routers.policy_events
import app.routers.requests  # type: ignore
sys.modules['server.app.routers.requests'] = app.routers.requests
import app.routers.commands  # type: ignore
sys.modules['server.app.routers.commands'] = app.routers.commands
import app.routers.enroll  # type: ignore
sys.modules['server.app.routers.enroll'] = app.routers.enroll
import app.daily_time  # type: ignore
sys.modules['server.app.daily_time'] = app.daily_time
import app.main  # type: ignore
sys.modules['server.app.main'] = app.main

import blocker  # type: ignore
sys.modules['agent.blocker'] = blocker
import local_cache  # type: ignore
sys.modules['agent.local_cache'] = local_cache
import tracker  # type: ignore
sys.modules['agent.tracker'] = tracker
import safe_browser  # type: ignore
sys.modules['agent.safe_browser'] = safe_browser
import ws_client  # type: ignore
sys.modules['agent.ws_client'] = ws_client
import main_service  # type: ignore
sys.modules['agent.main_service'] = main_service

try:
    import pytest  # type: ignore
except ImportError:
    pytest = None


if pytest is not None:
    @pytest.fixture(scope="session", autouse=True)
    def ensure_clean_db_around_all_tests():
        """Đảm bảo cơ sở dữ liệu luôn sạch 100% trước và sau khi chạy toàn bộ test suite."""
        app.websocket_manager.manager.active_connections.clear()
        db = app.database.SessionLocal()
        try:
            app.routers.policy_events.reset_system_state(db)
        finally:
            db.close()

        yield

        app.websocket_manager.manager.active_connections.clear()
        db = app.database.SessionLocal()
        try:
            app.routers.policy_events.reset_system_state(db)
        finally:
            db.close()
