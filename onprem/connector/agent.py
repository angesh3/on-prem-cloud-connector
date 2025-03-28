import asyncio
import aiohttp
import ssl
import logging
from typing import Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime, timedelta
import os
from fastapi import FastAPI, Request, HTTPException
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
connector = None

class OnPremConnector:
    def __init__(
        self,
        device_id: str,
        cloud_url: str,
        cert_path: str,
        key_path: str,
        chunk_size: int = 8192
    ):
        self.device_id = device_id
        self.cloud_url = cloud_url.rstrip('/')
        self.cert_path = cert_path
        self.key_path = key_path
        self.chunk_size = chunk_size
        self.token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        
        # SSL context for mutual TLS only if using HTTPS
        self.ssl_context = None
        if self.cloud_url.startswith('https://'):
            self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            self.ssl_context.load_cert_chain(cert_path, key_path)

    async def register_and_get_token(self) -> bool:
        """Register the device and obtain an authentication token"""
        try:
            registry_url = self.cloud_url.replace("reverse-proxy:8001", "registry:8000")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{registry_url}/register",
                    json={"device_id": self.device_id},
                    ssl=self.ssl_context
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.token = data["token"]
                        # Set token expiry (e.g., 1 hour from now)
                        self.token_expiry = datetime.now() + timedelta(hours=1)
                        logger.info("Successfully registered and obtained token")
                        return True
                    else:
                        logger.error(f"Registration failed: {await response.text()}")
                        return False
        except Exception as e:
            logger.error(f"Error during registration: {str(e)}")
            return False

    async def publish_data(self, data: Dict[str, Any], stream: bool = True) -> bool:
        """Publish data to cloud using chunked streaming for large payloads"""
        if not self.token or datetime.now() >= self.token_expiry:
            if not await self.register_and_get_token():
                return False

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        try:
            if stream and isinstance(data, (dict, list)):
                # Convert data to JSON string for streaming
                json_data = json.dumps(data)
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.cloud_url}/pubsub/publish",
                        headers=headers,
                        data=self._stream_data(json_data),
                        chunked=True,
                        ssl=self.ssl_context
                    ) as response:
                        if response.status == 200:
                            logger.info("Successfully published data")
                            return True
                        else:
                            logger.error(f"Failed to publish data: {await response.text()}")
                            return False
            else:
                # For small payloads, send directly
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.cloud_url}/pubsub/publish",
                        headers=headers,
                        json=data,
                        ssl=self.ssl_context
                    ) as response:
                        return response.status == 200
        except Exception as e:
            logger.error(f"Error publishing data: {str(e)}")
            return False

    async def _stream_data(self, data: str):
        """Generator for streaming large data in chunks"""
        for i in range(0, len(data), self.chunk_size):
            chunk = data[i:i + self.chunk_size]
            yield chunk.encode('utf-8')
            await asyncio.sleep(0.01)  # Prevent overwhelming the network

    async def handle_api_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming API requests from the cloud"""
        try:
            # Forward request to local application
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://localhost:8080/api",  # Local application endpoint
                    json=request_data
                ) as response:
                    return await response.json()
        except Exception as e:
            logger.error(f"Error handling API request: {str(e)}")
            return {"error": str(e)}

    async def start(self):
        """Start the connector service"""
        retry_count = 0
        max_retries = 5
        while retry_count < max_retries:
            try:
                if await self.register_and_get_token():
                    logger.info("On-Prem Connector started successfully")
                    break
                else:
                    retry_count += 1
                    wait_time = min(30, 2 ** retry_count)  # Exponential backoff
                    logger.info(f"Registration attempt {retry_count} failed, waiting {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
            except Exception as e:
                retry_count += 1
                wait_time = min(30, 2 ** retry_count)
                logger.error(f"Error in connector service: {str(e)}")
                logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count}/{max_retries})")
                await asyncio.sleep(wait_time)
        
        if retry_count >= max_retries:
            raise Exception("Failed to register after maximum retries")
        
        # Keep the connector running
        while True:
            try:
                # Refresh token if needed
                if self.token_expiry and datetime.now() >= self.token_expiry:
                    await self.register_and_get_token()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in connector service: {str(e)}")
                await asyncio.sleep(5)  # Wait before retrying

@app.post("/test")
async def test_endpoint(request: Request):
    """Test endpoint that echoes back the request data"""
    try:
        data = await request.json()
        return {"message": "success", "data": data}
    except Exception as e:
        logger.error(f"Error in test endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/status")
async def status_endpoint(request: Request):
    """Status endpoint that returns device status and diagnostics"""
    try:
        data = await request.json()
        include_diagnostics = data.get("include_diagnostics", False)
        
        response = {
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "device_id": connector.device_id if connector else None,
        }
        
        if include_diagnostics:
            response["diagnostics"] = {
                "token_valid": bool(connector and connector.token and connector.token_expiry > datetime.now()),
                "cloud_url": connector.cloud_url if connector else None,
                "ssl_enabled": bool(connector and connector.ssl_context)
            }
        
        return response
    except Exception as e:
        logger.error(f"Error in status endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def run_server():
    """Run the FastAPI server"""
    config = uvicorn.Config(app, host="0.0.0.0", port=8002)
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    """Main function to run both the connector and the server"""
    global connector
    connector = OnPremConnector(
        device_id=os.getenv("DEVICE_ID", "device001"),
        cloud_url=os.getenv("CLOUD_URL", "http://reverse-proxy:8001"),
        cert_path=os.getenv("CERT_PATH", "/certs/device.crt"),
        key_path=os.getenv("KEY_PATH", "/certs/device.key")
    )
    
    # Run both the connector and server
    await asyncio.gather(
        connector.start(),
        run_server()
    )

if __name__ == "__main__":
    asyncio.run(main()) 