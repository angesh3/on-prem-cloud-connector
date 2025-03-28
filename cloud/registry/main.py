from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import os
from token_manager import TokenManager
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize TokenManager
token_manager = TokenManager(
    secret_key=os.getenv("JWT_SECRET_KEY", "your-secret-key"),
    token_expiry_hours=1,
    ca_cert_path=os.getenv("CA_CERT_PATH")
)

# Load saved state if available
state_file = os.getenv("STATE_FILE", "device_registry_state.json")
if os.path.exists(state_file):
    token_manager.load_state(state_file)

class DeviceRegistration(BaseModel):
    device_id: str
    metadata: Optional[Dict[str, Any]] = None

class DeviceMetadata(BaseModel):
    metadata: Dict[str, Any]

async def verify_token(authorization: str = Header(None)):
    """Verify JWT token from Authorization header"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    try:
        token = authorization.split(" ")[1]
        device_info = token_manager.validate_token(token)
        if not device_info:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return device_info
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.post("/register")
async def register_device(registration: DeviceRegistration):
    """Register a new device and return its token"""
    try:
        result = token_manager.register_device(
            registration.device_id,
            registration.metadata
        )
        return result
    except Exception as e:
        logger.error(f"Error registering device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/device/{device_id}")
async def get_device_info(device_id: str, _: dict = Depends(verify_token)):
    """Get information about a registered device"""
    device_info = token_manager.get_device_info(device_id)
    if not device_info:
        raise HTTPException(status_code=404, detail="Device not found")
    return device_info

@app.put("/device/{device_id}/metadata")
async def update_device_metadata(
    device_id: str,
    metadata: DeviceMetadata,
    device_info: dict = Depends(verify_token)
):
    """Update device metadata"""
    if device_info["device_id"] != device_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this device")
    
    if not token_manager.update_device_metadata(device_id, metadata.metadata):
        raise HTTPException(status_code=404, detail="Device not found")
    
    return {"status": "success"}

@app.delete("/device/{device_id}")
async def revoke_device(
    device_id: str,
    device_info: dict = Depends(verify_token)
):
    """Revoke a device's registration"""
    if device_info["device_id"] != device_id:
        raise HTTPException(status_code=403, detail="Not authorized to revoke this device")
    
    if not token_manager.revoke_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    
    return {"status": "success"}

@app.post("/cleanup")
async def cleanup_expired_devices(_: dict = Depends(verify_token)):
    """Clean up expired device registrations"""
    removed_count = token_manager.cleanup_expired_devices()
    return {"removed_devices": removed_count}

@app.post("/device/{device_id}/data")
async def publish_data(
    device_id: str,
    data: Dict[str, Any],
    device_info: dict = Depends(verify_token)
):
    """Publish data for a device"""
    if device_info["device_id"] != device_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to publish data for this device"
        )
    
    try:
        # Store the data
        device_data = token_manager.get_device_info(device_id)
        if not device_data:
            raise HTTPException(status_code=404, detail="Device not found")
        
        # Update last seen timestamp
        device_data["last_seen"] = datetime.now()
        
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Error publishing data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/devices")
async def list_devices():
    """Get list of all registered devices"""
    devices = []
    now = datetime.now()
    for device_id, info in token_manager.devices.items():
        # Consider device connected if seen in last 30 seconds
        connected = (now - datetime.fromtimestamp(info["last_seen"])).total_seconds() < 30
        devices.append({
            "id": device_id,
            "status": "registered",
            "connected": connected,
            "last_seen": datetime.fromtimestamp(info["last_seen"]).isoformat(),
            "metadata": info["metadata"]
        })
    return devices

if __name__ == "__main__":
    import uvicorn
    
    # Load saved state if available
    state_file = os.getenv("STATE_FILE", "device_registry_state.json")
    if os.path.exists(state_file):
        token_manager.load_state(state_file)
    
    # Start the server
    uvicorn.run(app, host="0.0.0.0", port=8000) 