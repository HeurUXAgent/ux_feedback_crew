from fastapi import WebSocket
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        self.active_connections.pop(client_id, None)

    async def send_progress(self, client_id: str, message: str, step: int):
        ws = self.active_connections.get(client_id)
        if ws:
            await ws.send_json({
                "message": message,
                "step": step,
                "status": "processing"
            })

manager = ConnectionManager()

def safe_emit(client_id: str, message: str, step: int):
    """
    Can be called from sync code safely
    """
    try:
        # get the existing loop from the main FastAPI thread
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                manager.send_progress(client_id, message, step), 
                loop
            )
        else:
            loop.run_until_complete(manager.send_progress(client_id, message, step))
    except Exception as e:
        # Fallback for worker threads
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        new_loop.run_until_complete(manager.send_progress(client_id, message, step))
        new_loop.close()