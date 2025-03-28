from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class Permission(str, Enum):
    REGISTER_DEVICE = "register_device"
    DEREGISTER_DEVICE = "deregister_device"
    PUBLISH_DATA = "publish_data"
    READ_DATA = "read_data"
    MANAGE_ROLES = "manage_roles"

class Role(BaseModel):
    name: str
    permissions: List[Permission]
    description: Optional[str] = None

class DeviceMetadata(BaseModel):
    url: str
    description: str
    capabilities: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    environment: str = "production"
    version: str = "1.0.0"

class DeviceRegistration(BaseModel):
    device_id: str
    metadata: DeviceMetadata

class TokenResponse(BaseModel):
    token: str
    expires_at: datetime
    device_id: str
    role: str

class DeviceStatus(BaseModel):
    device_id: str
    status: str
    last_seen: datetime
    metadata: DeviceMetadata
    role: str 