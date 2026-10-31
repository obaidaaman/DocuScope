from typing import Dict, List, Any
from fastapi import WebSocket
import json
import asyncio

class ConnectionManager:
    def __init__(self):
        # Maps thread_id -> list of active WebSockets
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, thread_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            if thread_id not in self.active_connections:
                self.active_connections[thread_id] = []
            self.active_connections[thread_id].append(websocket)
        print(f"[WS connected Thread: {thread_id} Total clients: {len(self.active_connections.get(thread_id, []))}")

    async def disconnect(self, thread_id: str, websocket: WebSocket):
        async with self._lock:
            if thread_id in self.active_connections:
                if websocket in self.active_connections[thread_id]:
                    self.active_connections[thread_id].remove(websocket)
                if not self.active_connections[thread_id]:
                    del self.active_connections[thread_id]
        print(f"WS disconnected Thread: {thread_id}")

    async def broadcast(self, thread_id: str, event_type: str, data: Any):
        async with self._lock:
            connections = list(self.active_connections.get(thread_id, []))

        if not connections:
            return

        message = {
            "thread_id": thread_id,
            "event": event_type,
            "data": data
        }
        raw_msg = json.dumps(message)
        dead_connections = []

        for ws in connections:
            try:
                await ws.send_text(raw_msg)
            except Exception as e:
                print(f"WS error Failed to send message to thread {thread_id}: {e}")
                dead_connections.append(ws)

        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    if thread_id in self.active_connections and ws in self.active_connections[thread_id]:
                        self.active_connections[thread_id].remove(ws)

ws_manager = ConnectionManager()
