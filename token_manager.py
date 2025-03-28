import jwt
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import ssl
import json
import os
import logging

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
        self.devices: Dict[str, Dict[str, Any]] = {}
        
        # SSL context for mutual TLS
        self.ssl_context = None
        if ca_cert_path:
            self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            self.ssl_context.load_verify_locations(ca_cert_path)

    def register_device(
        self,
        device_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Register a new device and return its token"""
        if device_id in self.devices:
            # Update existing device
            self.devices[device_id]["metadata"] = metadata or {}
            self.devices[device_id]["last_seen"] = time.time()
        else:
            # Register new device
            self.devices[device_id] = {
                "device_id": device_id,
                "metadata": metadata or {},
                "registered_at": time.time(),
                "last_seen": time.time()
            }
        
        # Generate token
        token = self._generate_token(device_id)
        
        return {
            "token": token,
            "expires_in": self.token_expiry_hours * 3600,
            "device_id": device_id
        }

    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate JWT token and return device info"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            device_id = payload.get("device_id")
            
            if not device_id or device_id not in self.devices:
                return None
            
            # Update last seen timestamp
            self.devices[device_id]["last_seen"] = time.time()
            
            return self.devices[device_id]
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            return None

    def get_device_info(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get device information"""
        return self.devices.get(device_id)

    def update_device_metadata(
        self,
        device_id: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """Update device metadata"""
        if device_id not in self.devices:
            return False
        
        self.devices[device_id]["metadata"].update(metadata)
        self.devices[device_id]["last_seen"] = time.time()
        return True

    def revoke_device(self, device_id: str) -> bool:
        """Revoke a device's registration"""
        if device_id not in self.devices:
            return False
        
        del self.devices[device_id]
        return True

    def cleanup_expired_devices(self, max_age_hours: int = 24) -> int:
        """Remove devices that haven't been seen for a while"""
        current_time = time.time()
        max_age = max_age_hours * 3600
        
        expired_devices = [
            device_id for device_id, info in self.devices.items()
            if current_time - info["last_seen"] > max_age
        ]
        
        for device_id in expired_devices:
            del self.devices[device_id]
        
        return len(expired_devices)

    def _generate_token(self, device_id: str) -> str:
        """Generate JWT token for device"""
        payload = {
            "device_id": device_id,
            "exp": datetime.utcnow() + timedelta(hours=self.token_expiry_hours)
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def save_state(self, filename: str):
        """Save device registry state to file"""
        with open(filename, "w") as f:
            json.dump(self.devices, f)

    def load_state(self, filename: str):
        """Load device registry state from file"""
        try:
            with open(filename, "r") as f:
                self.devices = json.load(f)
        except FileNotFoundError:
            logger.warning(f"State file {filename} not found") 