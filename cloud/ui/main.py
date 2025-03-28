import os
import logging
from fastapi import FastAPI, Request, HTTPException, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import aiohttp
import json
from datetime import datetime
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# In-memory storage for published data (in production, use a proper database)
published_data = []

# Store WebSocket connections for each device
device_connections = {}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the cloud UI dashboard"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "published_data": published_data
    })

@app.post("/receive-data")
async def receive_data(request: Request):
    """Endpoint to receive published data from devices"""
    try:
        data = await request.json()
        data["timestamp"] = datetime.now().isoformat()
        published_data.append(data)
        # Keep only last 100 messages
        if len(published_data) > 100:
            published_data.pop(0)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error receiving data: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    await websocket.accept()
    device_connections[device_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            # Echo back for now
            await websocket.send_text(f"Message received: {data}")
    except:
        if device_id in device_connections:
            del device_connections[device_id]

@app.get("/api/devices")
async def get_devices():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://registry:8000/devices") as response:
            devices = await response.json()
            return devices

@app.get("/api/device/{device_id}")
async def get_device(device_id: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://registry:8000/device/{device_id}") as response:
            device = await response.json()
            return device

@app.post("/api/invoke/{device_id}")
async def invoke_api(device_id: str, request: Request):
    body = await request.json()
    endpoint = body.get("endpoint", "").strip()
    data = body.get("data", {})
    
    if not endpoint:
        raise HTTPException(status_code=400, detail="Endpoint is required")
    
    # Remove leading slash if present
    if endpoint.startswith("/"):
        endpoint = endpoint[1:]
    
    # First, get the device token from registry
    async with aiohttp.ClientSession() as session:
        # Get device token
        async with session.post(
            "http://registry:8000/register",
            json={
                "device_id": device_id,
                "metadata": {
                    "url": "http://onprem-connector:8002",
                    "description": "Test Device"
                }
            }
        ) as token_response:
            if token_response.status != 200:
                raise HTTPException(status_code=token_response.status, detail="Failed to get device token")
            token_data = await token_response.json()
            token = token_data["token"]

        # Now make the request to the reverse proxy with the token
        async with session.post(
            f"http://reverse-proxy:8001/forward/{device_id}/{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            json=data
        ) as response:
            try:
                result = await response.json()
                return result
            except:
                # If response is not JSON, return text
                text = await response.text()
                return {"response": text}

@app.get("/api/published-data")
async def get_published_data():
    """Return the published data for visualization"""
    return published_data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003) 