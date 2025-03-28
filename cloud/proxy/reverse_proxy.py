from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import aiohttp
import logging
from typing import Optional, Dict, Any
import os
import jwt
import asyncio
import hashlib
import ssl

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

# Get JWT secret key from environment
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://registry:8000")

class ChunkedTransfer:
    def __init__(self, chunk_size: int = 8192):
        self.chunk_size = chunk_size
        self.checksum = hashlib.sha256()

    async def stream_request(self, request: Request):
        """Stream request data in chunks"""
        async for chunk in request.stream():
            self.checksum.update(chunk)
            yield chunk

    async def stream_response(self, response: aiohttp.ClientResponse):
        """Stream response data in chunks"""
        async for chunk in response.content.iter_chunked(self.chunk_size):
            yield chunk

async def verify_token(request: Request):
    """Verify JWT token from Authorization header"""
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    try:
        token = authorization.split(" ")[1]
        # Decode the token to get the device ID
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        device_id = payload.get("device_id")
        
        if not device_id:
            raise HTTPException(status_code=401, detail="Invalid token: no device ID")
        
        # Get device info from registry
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{REGISTRY_URL}/device/{device_id}",
                headers={"Authorization": f"Bearer {token}"}
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=401, detail="Invalid or expired token")
                device_info = await response.json()
                return device_info
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Error verifying token: {str(e)}")
        raise HTTPException(status_code=401, detail=str(e))

@app.post("/forward/{device_id}/{endpoint:path}")
async def forward_request(
    device_id: str,
    endpoint: str,
    request: Request,
    device_info: dict = Depends(verify_token)
):
    """Forward API requests to on-premise device with streaming support"""
    if device_info["device_id"] != device_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this device"
        )

    device_url = device_info.get("metadata", {}).get("url")
    if not device_url:
        raise HTTPException(
            status_code=400,
            detail="Device URL not configured"
        )

    try:
        # Prepare headers
        headers = {k: v for k, v in request.headers.items() if k.lower() != 'content-length'}
        headers["X-Forwarded-For"] = request.client.host
        headers["X-Original-URI"] = str(request.url)

        # Create SSL context for the connection
        ssl_context = None
        if os.getenv("CA_CERT_PATH"):
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_verify_locations(os.getenv("CA_CERT_PATH"))
            ssl_context.verify_mode = ssl.CERT_REQUIRED

        # Forward the request
        async with aiohttp.ClientSession() as session:
            # Read the entire request body first
            body = await request.body()
            
            async with session.request(
                method=request.method,
                url=f"{device_url}/{endpoint}",
                headers=headers,
                data=body,  # Send the body directly
                ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=3600)  # 1 hour timeout
            ) as response:
                # Read the response body
                response_body = await response.read()
                
                # Return the response with the original content type
                return Response(
                    content=response_body,
                    status_code=response.status,
                    headers=dict(response.headers),
                    media_type=response.headers.get("content-type")
                )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Request timed out"
        )
    except Exception as e:
        logger.error(f"Error forwarding request: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Error forwarding request: {str(e)}"
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001) 