import jwt
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
import yaml
import hashlib
from cryptography.fernet import Fernet
from .models import Role, Permission, DeviceMetadata

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TokenManager:
    def __init__(self, secret_key: str, config_path: str = "/etc/config/config.yaml"):
        self.secret_key = secret_key
        self.encryption_key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.encryption_key)
        self.registered_devices: Dict[str, dict] = {}
        self.roles: Dict[str, Role] = self._initialize_roles()
        self.config = self._load_config(config_path)
        self.logger = logging.getLogger(__name__)
        
        # Start token rotation task
        if self.config["token_rotation"]["enabled"]:
            asyncio.create_task(self._rotate_tokens_periodically())

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from yaml file"""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return {
                "token_rotation": {"enabled": True, "interval_hours": 24},
                "security": {"min_tls_version": "TLS1.2", "enable_mtls": True}
            }

    def _initialize_roles(self) -> Dict[str, Role]:
        """Initialize default roles and permissions"""
        return {
            "admin": Role(
                name="admin",
                permissions=[
                    Permission.REGISTER_DEVICE,
                    Permission.DEREGISTER_DEVICE,
                    Permission.PUBLISH_DATA,
                    Permission.READ_DATA,
                    Permission.MANAGE_ROLES
                ]
            ),
            "device": Role(
                name="device",
                permissions=[
                    Permission.PUBLISH_DATA,
                    Permission.READ_DATA
                ]
            ),
            "reader": Role(
                name="reader",
                permissions=[
                    Permission.READ_DATA
                ]
            )
        }

    async def _rotate_tokens_periodically(self):
        """Periodically rotate tokens for all registered devices"""
        while True:
            interval_hours = self.config["token_rotation"]["interval_hours"]
            await asyncio.sleep(interval_hours * 3600)
            
            try:
                for device_id in self.registered_devices:
                    if self.registered_devices[device_id]["status"] == "active":
                        new_token = self._generate_token(
                            device_id,
                            self.registered_devices[device_id]["metadata"]
                        )
                        self.registered_devices[device_id]["token"] = new_token
                        self.logger.info(f"Rotated token for device {device_id}")
            except Exception as e:
                self.logger.error(f"Token rotation failed: {e}")

    def _generate_token(self, device_id: str, metadata: DeviceMetadata) -> str:
        """Generate a new JWT token"""
        expiration = datetime.utcnow() + timedelta(hours=self.config["token_rotation"]["interval_hours"])
        payload = {
            "device_id": device_id,
            "metadata": metadata.dict(),
            "role": "device",
            "iat": datetime.utcnow(),
            "exp": expiration
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def _encrypt_sensitive_data(self, data: str) -> bytes:
        """Encrypt sensitive data before storing"""
        return self.cipher_suite.encrypt(data.encode())

    def _decrypt_sensitive_data(self, encrypted_data: bytes) -> str:
        """Decrypt sensitive data"""
        return self.cipher_suite.decrypt(encrypted_data).decode()

    def register_device(self, device_id: str, metadata: DeviceMetadata) -> str:
        """Register a device and generate token"""
        if device_id in self.registered_devices:
            self.logger.warning(f"Device {device_id} already registered, updating metadata")
            
        token = self._generate_token(device_id, metadata)
        encrypted_metadata = self._encrypt_sensitive_data(metadata.json())
        
        self.registered_devices[device_id] = {
            "token": token,
            "metadata": encrypted_metadata,
            "last_seen": datetime.utcnow(),
            "status": "active",
            "role": "device"
        }
        
        self.logger.info(f"Device {device_id} registered successfully")
        return token

    def validate_token(self, token: str) -> bool:
        """Validate token and check permissions"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            device_id = payload["device_id"]
            
            if device_id not in self.registered_devices:
                return False
                
            if self.registered_devices[device_id]["status"] != "active":
                return False
                
            self.registered_devices[device_id]["last_seen"] = datetime.utcnow()
            return True
            
        except jwt.InvalidTokenError as e:
            self.logger.error(f"Token validation failed: {e}")
            return False

    def check_permission(self, token: str, required_permission: Permission) -> bool:
        """Check if token has required permission"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            role_name = payload.get("role")
            
            if role_name not in self.roles:
                return False
                
            return required_permission in self.roles[role_name].permissions
            
        except jwt.InvalidTokenError:
            return False

    def revoke_device(self, device_id: str):
        """Revoke device registration"""
        if device_id in self.registered_devices:
            self.registered_devices[device_id]["status"] = "revoked"
            self.logger.info(f"Device {device_id} revoked")
        else:
            raise ValueError(f"Device {device_id} not found")

    def get_device_info(self, device_id: str) -> Optional[dict]:
        """Get device information"""
        if device_id in self.registered_devices:
            device_info = self.registered_devices[device_id].copy()
            # Decrypt metadata before returning
            device_info["metadata"] = self._decrypt_sensitive_data(device_info["metadata"])
            return device_info
        return None

    def cleanup_expired_devices(self):
        """Remove devices that haven't been seen for a long time"""
        current_time = datetime.utcnow()
        expired_devices = []
        
        for device_id, info in self.registered_devices.items():
            last_seen = info["last_seen"]
            if (current_time - last_seen).days > 30:  # Configure expiry period
                expired_devices.append(device_id)
                
        for device_id in expired_devices:
            del self.registered_devices[device_id]
            self.logger.info(f"Removed expired device {device_id}")

    def save_state(self, file_path: str):
        """Save the current state to a file"""
        state = {
            device_id: {
                **info,
                "last_seen": info["last_seen"].isoformat()
            }
            for device_id, info in self.registered_devices.items()
        }
        
        with open(file_path, 'w') as f:
            json.dump(state, f, indent=2)

    def load_state(self, file_path: str):
        """Load state from a file"""
        try:
            with open(file_path, 'r') as f:
                state = json.load(f)
            
            self.registered_devices = {
                device_id: {
                    **info,
                    "last_seen": datetime.fromisoformat(info["last_seen"])
                }
                for device_id, info in state.items()
            }
        except FileNotFoundError:
            logger.warning(f"State file {file_path} not found")
        except Exception as e:
            logger.error(f"Error loading state: {str(e)}")
            raise 