from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import aiohttp
import os
import logging
from pathlib import Path
import json
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum
import httpx

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ErrorCode(Enum):
    DEVICE_NOT_REGISTERED = "DEVICE_NOT_REGISTERED"
    NETWORK_ERROR = "NETWORK_ERROR"
    INVALID_DATA = "INVALID_DATA"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    CLOUD_SERVICE_ERROR = "CLOUD_SERVICE_ERROR"

class DeviceError(Exception):
    def __init__(self, code: ErrorCode, message: str, details: Optional[str] = None):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Global variables for device status
device_status = {
    "registered": False,
    "connected": False,
    "device_id": os.getenv("DEVICE_ID", "device001"),
    "token": None,
    "last_heartbeat": None,
    "registration_info": None
}

async def check_device_status():
    """Background task to check device connection status"""
    while True:
        try:
            cloud_url = os.getenv("CLOUD_URL", "http://registry:8000")
            if device_status["token"]:
                async with aiohttp.ClientSession() as session:
                    headers = {"Authorization": f"Bearer {device_status['token']}"}
                    async with session.get(
                        f"{cloud_url}/device/{device_status['device_id']}",
                        headers=headers
                    ) as response:
                        if response.status == 200:
                            device_status["connected"] = True
                            device_status["last_heartbeat"] = datetime.now().isoformat()
                        else:
                            device_status["connected"] = False
                            device_status["last_heartbeat"] = "Disconnected"
        except Exception as e:
            device_status["connected"] = False
            device_status["last_heartbeat"] = f"Error: {str(e)}"
        
        await asyncio.sleep(30)  # Check every 30 seconds

@app.on_event("startup")
async def startup_event():
    """Start background tasks"""
    asyncio.create_task(check_device_status())

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the main dashboard"""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "device_status": device_status
        }
    )

@app.post("/register")
async def register_device(
    request: Request,
    device_id: str = Form(...),
    metadata: str = Form(...)
):
    """Register a device with the cloud service"""
    try:
        cloud_url = os.getenv("CLOUD_URL", "http://registry:8000")
        cert_path = os.getenv("CERT_PATH")
        key_path = os.getenv("KEY_PATH")

        # Prepare SSL context if certificates are available
        ssl_context = None
        if cert_path and key_path:
            ssl_context = aiohttp.TCPConnector(
                ssl=False
            )

        async with aiohttp.ClientSession(connector=ssl_context) as session:
            async with session.post(
                f"{cloud_url}/register",
                json={
                    "device_id": device_id,
                    "metadata": json.loads(metadata)
                }
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    device_status.update({
                        "registered": True,
                        "device_id": device_id,
                        "token": result["token"],
                        "registration_info": result
                    })
                    return {"status": "success", "data": result}
                else:
                    error_msg = await response.text()
                    raise HTTPException(status_code=response.status, detail=error_msg)
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.exception_handler(DeviceError)
async def device_error_handler(request: Request, exc: DeviceError):
    logger.error(f"Device error: {exc.code} - {exc.message} - Details: {exc.details}")
    return JSONResponse(
        status_code=400,
        content={
            "code": exc.code.value,
            "message": exc.message,
            "details": exc.details
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTP error: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": "HTTP_ERROR",
            "message": str(exc.detail),
            "status_code": exc.status_code
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "details": str(exc)
        }
    )

async def validate_device_registration():
    """Validate device registration status"""
    if not device_status["registered"]:
        raise DeviceError(
            code=ErrorCode.DEVICE_NOT_REGISTERED,
            message="Device is not registered",
            details="Please register the device before performing this operation"
        )

@app.post("/publish")
async def publish_data(data: Dict[str, Any]):
    """Publish data to the cloud service with enhanced error handling"""
    await validate_device_registration()

    try:
        # Ensure data has required fields
        if not isinstance(data, dict):
            raise DeviceError(
                code=ErrorCode.INVALID_DATA,
                message="Invalid data format",
                details="Data must be a dictionary"
            )

        # Add timestamp if not present
        if "timestamp" not in data:
            data["timestamp"] = datetime.now().isoformat()

        # Use cloud-ui service name for Docker network communication
        cloud_url = "http://cloud-ui:8003"  # Changed from registry:8000
        device_id = device_status["device_id"]
        token = device_status["token"]

        if not token:
            raise DeviceError(
                code=ErrorCode.AUTHENTICATION_ERROR,
                message="Device token not found",
                details="Please register the device to obtain a valid token"
            )

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token}"}
            async with session.post(
                f"{cloud_url}/receive-data",  # Changed from /device/{device_id}/data
                headers=headers,
                json=data
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"status": "success", "data": result}
                else:
                    error_text = await response.text()
                    logger.error(f"Error publishing data: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Failed to publish data: {error_text}"
                    )

    except aiohttp.ClientError as e:
        logger.error(f"Network error while publishing data: {str(e)}")
        raise DeviceError(
            code=ErrorCode.NETWORK_ERROR,
            message="Failed to connect to cloud service",
            details=str(e)
        )
    except Exception as e:
        logger.error(f"Error publishing data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/invoke-api")
async def invoke_api(request: Dict[str, Any]):
    """Invoke an API endpoint with enhanced error handling"""
    await validate_device_registration()

    try:
        # Validate request format
        if not isinstance(request, dict):
            raise DeviceError(
                code=ErrorCode.INVALID_DATA,
                message="Invalid request format",
                details="Request must be a JSON object"
            )
        
        if "endpoint" not in request:
            raise DeviceError(
                code=ErrorCode.INVALID_DATA,
                message="Missing endpoint",
                details="Request must include 'endpoint' field"
            )
            
        if "payload" not in request:
            request["payload"] = {}  # Default to empty payload if not provided

        # Use reverse-proxy service name for Docker network communication
        proxy_url = os.getenv("REVERSE_PROXY_URL", "http://reverse-proxy:8001")
        
        # Ensure endpoint starts with a slash
        endpoint = request["endpoint"]
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"

        # Construct the full URL
        full_url = f"{proxy_url}/forward/{device_status['device_id']}{endpoint}"
        
        # Add token to headers
        headers = {
            "Authorization": f"Bearer {device_status['token']}",
            "Content-Type": "application/json"
        }

        logger.info(f"Invoking API at {full_url}")
        logger.info(f"Payload: {json.dumps(request['payload'])}")
        logger.info(f"Headers: {headers}")  # Log headers for debugging

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    full_url,
                    headers=headers,
                    json=request['payload'],
                    timeout=30  # Increased timeout
                ) as response:
                    response_text = await response.text()
                    logger.info(f"Response status: {response.status}")
                    logger.info(f"Response text: {response_text}")

                    if response.status == 200:
                        try:
                            result = json.loads(response_text)
                        except json.JSONDecodeError:
                            result = {"raw_response": response_text}
                            
                        return {
                            "status": "success",
                            "data": result,
                            "status_code": response.status
                        }
                    else:
                        raise DeviceError(
                            code=ErrorCode.CLOUD_SERVICE_ERROR,
                            message=f"API invocation failed with status {response.status}",
                            details=response_text
                        )
            except aiohttp.ClientError as e:
                logger.error(f"Network error: {str(e)}")
                raise DeviceError(
                    code=ErrorCode.NETWORK_ERROR,
                    message="Network error while invoking API",
                    details=str(e)
                )
    except DeviceError:
        raise
    except Exception as e:
        logger.error("Unexpected error while invoking API", exc_info=True)
        raise DeviceError(
            code=ErrorCode.CLOUD_SERVICE_ERROR,
            message="Failed to invoke API",
            details=str(e)
        )

@app.get("/status")
async def get_status():
    """Get current device status"""
    try:
        if device_status["registered"]:
            cloud_url = os.getenv("CLOUD_URL", "http://registry:8000")
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {device_status['token']}"}
                async with session.get(
                    f"{cloud_url}/device/{device_status['device_id']}",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        device_info = await response.json()
                        device_status.update({
                            "connected": True,
                            "last_heartbeat": datetime.now().isoformat(),
                            "registration_info": device_info
                        })
                    else:
                        device_status["connected"] = False
                        device_status["last_heartbeat"] = "Disconnected"
        return device_status
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        device_status["connected"] = False
        device_status["last_heartbeat"] = f"Error: {str(e)}"
        return device_status

@app.get("/api/devices")
async def list_devices():
    """Get list of all registered devices"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{REGISTRY_URL}/devices")
            return response.json()
    except Exception as e:
        logger.error(f"Error listing devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/deregister/{device_id}")
async def deregister_device(device_id: str):
    """Deregister a device from the cloud service"""
    try:
        cloud_url = os.getenv("CLOUD_URL", "http://registry:8000")
        cert_path = os.getenv("CERT_PATH")
        key_path = os.getenv("KEY_PATH")

        # Prepare SSL context if certificates are available
        ssl_context = None
        if cert_path and key_path:
            ssl_context = aiohttp.TCPConnector(
                ssl=False
            )

        async with aiohttp.ClientSession(connector=ssl_context) as session:
            async with session.post(
                f"{cloud_url}/deregister/{device_id}",
                headers={"Authorization": f"Bearer {device_status['token']}"} if device_status['token'] else {}
            ) as response:
                if response.status == 200:
                    # Reset device status
                    device_status.update({
                        "registered": False,
                        "connected": False,
                        "device_id": None,
                        "token": None,
                        "last_heartbeat": None,
                        "registration_info": None
                    })
                    return {"status": "success", "message": "Device deregistered successfully"}
                else:
                    error_msg = await response.text()
                    raise HTTPException(status_code=response.status, detail=error_msg)
    except Exception as e:
        logger.error(f"Deregistration error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080) 