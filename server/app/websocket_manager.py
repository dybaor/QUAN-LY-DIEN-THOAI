import asyncio
from collections import defaultdict
from typing import Dict, Iterable, Optional, Set

from fastapi import WebSocket


class ConnectionManager:
    """Quản lý kết nối WebSocket theo khóa `parent_*`, `child_*`, `agent_*`.

    Mỗi khóa có phạm vi trẻ (`scopes`) để lệnh chỉ đến đúng trẻ/thiết bị của phụ huynh sở hữu.
    Khóa không có phạm vi nhận mọi thông điệp cùng loại (dùng cho kiểm thử nội bộ).
    """

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.scopes: Dict[str, Set[int]] = {}

    async def connect(self, key: str, websocket: WebSocket, child_ids: Optional[Iterable[int]] = None):
        await websocket.accept()
        self.active_connections[key].add(websocket)
        if child_ids is not None:
            self.scopes[key] = set(child_ids)

    def disconnect(self, key: str, websocket: WebSocket = None):
        if key not in self.active_connections:
            return
        if websocket is None:
            self.active_connections[key].clear()
        else:
            self.active_connections[key].discard(websocket)
        if not self.active_connections[key]:
            del self.active_connections[key]
            self.scopes.pop(key, None)

    def update_scope(self, key_prefix: str, child_ids: Iterable[int]):
        for key in list(self.active_connections):
            if key.startswith(key_prefix):
                self.scopes[key] = set(child_ids)

    def _targets(self, prefix: str, child_id: Optional[int]):
        for key, connections in list(self.active_connections.items()):
            if not key.startswith(prefix):
                continue
            scope = self.scopes.get(key)
            if child_id is not None and scope is not None and child_id not in scope:
                continue
            yield key, list(connections)

    async def _send(self, prefix: str, child_id: Optional[int], payload, binary: bool = False) -> bool:
        delivered = False
        for _, connections in self._targets(prefix, child_id):
            for ws in connections:
                try:
                    sender = ws.send_bytes(payload) if binary else ws.send_json(payload)
                    await asyncio.wait_for(sender, timeout=0.5)
                    delivered = True
                except Exception:
                    pass
        return delivered

    async def send_command(self, key: str, command: dict) -> bool:
        delivered = False
        for ws in list(self.active_connections.get(key, set())):
            try:
                await asyncio.wait_for(ws.send_json(command), timeout=0.5)
                delivered = True
            except Exception:
                pass
        return delivered

    async def send_to_children(self, message: dict, child_id: Optional[int] = None) -> bool:
        return await self._send("child_", child_id, message)

    async def send_to_parents(self, message: dict, child_id: Optional[int] = None) -> bool:
        return await self._send("parent_", child_id, message)

    async def send_to_agents(self, message: dict, child_id: Optional[int] = None) -> bool:
        return await self._send("agent_", child_id, message)

    async def send_bytes_to_parents(self, data: bytes, child_id: Optional[int] = None) -> bool:
        return await self._send("parent_", child_id, data, binary=True)

    async def send_to_child_devices(self, message: dict, child_id: int):
        """Gửi tới cả cổng học tập (web) và Agent của một trẻ."""
        await self.send_to_children(message, child_id)
        await self.send_to_agents(message, child_id)

    async def notify_child(self, message: dict, child_id: int):
        """Gửi tới mọi bên liên quan đến một trẻ: phụ huynh sở hữu, cổng học tập và Agent."""
        await self.send_to_child_devices(message, child_id)
        await self.send_to_parents(message, child_id)

    async def broadcast(self, message: dict):
        for _, connections in list(self.active_connections.items()):
            for ws in list(connections):
                try:
                    await asyncio.wait_for(ws.send_json(message), timeout=0.5)
                except Exception:
                    pass

    def online_keys(self, prefix: str, child_id: Optional[int] = None) -> list:
        return [key for key, _ in self._targets(prefix, child_id)]


manager = ConnectionManager()
