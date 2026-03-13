from fastapi import WebSocket
import asyncio
import logging
import json

logger = logging.getLogger("ws_manager")


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"[WS] Client connected: {client_id}")

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            self.active_connections.pop(client_id)
            logger.info(f"[WS] Client disconnected: {client_id}")

    async def send_progress(self, client_id: str, message: str | dict, step: int):

        ws = self.active_connections.get(client_id)

        if not ws:
            logger.warning(f"[WS] No active websocket for client {client_id}")
            return

        payload = {
            "message": message,
            "step": step,
            "status": "processing"
        }

        try:
            logger.info(f"[WS SEND] -> {json.dumps(payload)[:200]}")
            await ws.send_json(payload)
            logger.info(f"[WS] Sent successfully to {client_id}")

        except Exception as e:
            logger.error(f"[WS ERROR] sending to {client_id}: {e}")


manager = ConnectionManager()


def safe_emit(client_id: str, message: str | dict, step: int):
    """
    Safe websocket emitter from any thread (CrewAI runs in worker threads)
    """

    logger.info(f"[WS EMIT] client={client_id} step={step}")

    try:
        loop = asyncio.get_running_loop()

        asyncio.run_coroutine_threadsafe(
            manager.send_progress(client_id, message, step),
            loop,
        )

    except RuntimeError:
        # If no running loop, fallback
        asyncio.run(manager.send_progress(client_id, message, step))