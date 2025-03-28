import jwt
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import ssl
from pathlib import Path
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TokenManager:
    def __init__(
        self,
        secret_key: str,
        token_expiry_hours: int = 1,
        ca_cert_path: Optional[str] = None
    ):
        self.secret_key = secret_key
        self.token_expiry_hours = token_expiry_hours
        self.registered_devices: Dict[str, dict] = {}
        
        # SSL context for validating client certificates
        if ca_cert_path:
            self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            self.ssl_context.load_verify_locations(ca_cert_path)
            self.ssl_context.verify_mode = ssl.CERT_REQUIRED
        else:
            self.ssl_context = None

    def register_device(self, device_id: str, metadata: dict = None) -> dict:
        """Register a new device and generate its token"""
        try:
            if device_id in self.registered_devices:
                logger.info(f"Device {device_id} already registered, updating token")
            else:
                logger.info(f"Registering new device: {device_id}")
            
            token = self._generate_token(device_id)
            
            self.registered_devices[device_id] = {
                "device_id": device_id,
                "metadata": metadata or {},
                "last_seen": datetime.now(),
                "token": token
            }
            
            return {
                "token": token,
                "expires_in": self.token_expiry_hours * 3600  # seconds
            }
        except Exception as e:
            logger.error(f"Error registering device {device_id}: {str(e)}")
            raise

    def validate_token(self, token: str) -> Optional[dict]:
        """Validate a device token and return the device information"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            device_id = payload.get("device_id")
            
            if device_id not in self.registered_devices:
                logger.warning(f"Token validation failed: Device {device_id} not registered")
                return None
            
            # Update last seen timestamp
            self.registered_devices[device_id]["last_seen"] = datetime.now()
            
            return self.registered_devices[device_id]
        except jwt.ExpiredSignatureError:
            logger.warning("Token validation failed: Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token validation failed: {str(e)}")
            return None

    def _generate_token(self, device_id: str) -> str:
        """Generate a JWT token for the device"""
        payload = {
            "device_id": device_id,
            "exp": datetime.utcnow() + timedelta(hours=self.token_expiry_hours),
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def get_device_info(self, device_id: str) -> Optional[dict]:
        """Get information about a registered device"""
        return self.registered_devices.get(device_id)

    def update_device_metadata(self, device_id: str, metadata: dict) -> bool:
        """Update metadata for a registered device"""
        if device_id in self.registered_devices:
            self.registered_devices[device_id]["metadata"].update(metadata)
            return True
        return False

    def revoke_device(self, device_id: str) -> bool:
        """Revoke a device's registration"""
        if device_id in self.registered_devices:
            del self.registered_devices[device_id]
            return True
        return False

    def cleanup_expired_devices(self, max_inactive_hours: int = 24) -> int:
        """Clean up devices that haven't been seen in a while"""
        now = datetime.now()
        expired = []
        
        for device_id, info in self.registered_devices.items():
            if (now - info["last_seen"]).total_seconds() > max_inactive_hours * 3600:
                expired.append(device_id)
        
        for device_id in expired:
            del self.registered_devices[device_id]
        
        return len(expired)

    def save_state(self, file_path: str):
        """Save the current state to a file"""
        state = {
            "devices": self.registered_devices,
            "secret_key": self.secret_key,
            "token_expiry_hours": self.token_expiry_hours
        }
        with open(file_path, "w") as f:
            json.dump(state, f)

    def load_state(self, file_path: str):
        """Load state from a file"""
        if not Path(file_path).exists():
            return
        
        with open(file_path, "r") as f:
            state = json.load(f)
            self.registered_devices = state["devices"]
            self.secret_key = state["secret_key"]
            self.token_expiry_hours = state["token_expiry_hours"] 