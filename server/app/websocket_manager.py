import asyncio
from typing import Dict, Set
from collections import defaultdict
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # Lưu trữ các kết nối đang active: {device_id: set of WebSockets}
        self.active_connections: Dict[str, Set[WebSocket]] = defaultdict(set)

    async def connect(self, device_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[device_id].add(websocket)
        print(f"[WS] Thiết bị kết nối: {device_id} (Tổng WS cho device: {len(self.active_connections[device_id])})")

    def disconnect(self, device_id: str, websocket: WebSocket = None):
        if device_id in self.active_connections:
            if websocket and websocket in self.active_connections[device_id]:
                self.active_connections[device_id].discard(websocket)
            elif not websocket:
                self.active_connections[device_id].clear()
            if not self.active_connections[device_id]:
                del self.active_connections[device_id]
            print(f"[WS] Thiết bị ngắt kết nối: {device_id}")

    async def send_command(self, device_id: str, command: dict) -> bool:
        """Gửi lệnh khẩn cấp xuống Agent (lock_now, extend_time, unlock)"""
        connections = self.active_connections.get(device_id, set())
        success = False
        for ws in list(connections):
            try:
                await asyncio.wait_for(ws.send_json(command), timeout=0.5)
                success = True
            except Exception:
                pass
        return success

    async def broadcast(self, message: dict):
        """Gửi thông điệp tới tất cả các Agent đang kết nối."""
        for device_id, connections in list(self.active_connections.items()):
            for ws in list(connections):
                try:
                    await asyncio.wait_for(ws.send_json(message), timeout=0.5)
                except Exception:
                    pass

    async def send_to_children(self, message: dict):
        """Chỉ gửi thông điệp tới các Cửa sổ Trẻ em (child_*)"""
        for device_id, connections in list(self.active_connections.items()):
            if str(device_id).startswith("child_"):
                for ws in list(connections):
                    try:
                        await asyncio.wait_for(ws.send_json(message), timeout=0.5)
                    except Exception:
                        pass

    async def send_to_parents(self, message: dict):
        """Chỉ gửi thông điệp tới các Dashboard Phụ huynh (parent_*)"""
        for device_id, connections in list(self.active_connections.items()):
            if str(device_id).startswith("parent_"):
                for ws in list(connections):
                    try:
                        await asyncio.wait_for(ws.send_json(message), timeout=0.5)
                    except Exception:
                        pass

    async def send_bytes_to_parents(self, data: bytes):
        """Chỉ gửi dữ liệu nhị phân (Binary Frame Video 15-30 FPS) tới các Dashboard Phụ huynh (parent_*)"""
        for device_id, connections in list(self.active_connections.items()):
            if str(device_id).startswith("parent_"):
                for ws in list(connections):
                    try:
                        await asyncio.wait_for(ws.send_bytes(data), timeout=0.5)
                    except Exception:
                        pass


manager = ConnectionManager()
