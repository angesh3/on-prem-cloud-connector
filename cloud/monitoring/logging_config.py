import logging
import logging.handlers
import os
from datetime import datetime

def setup_logging(service_name: str, log_level: str = "INFO"):
    """Configure logging for the service"""
    
    # Create logs directory if it doesn't exist
    log_dir = "/var/log/onprem-cloud-connector"
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure logging format
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set up file handler with rotation
    log_file = f"{log_dir}/{service_name}.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(log_format)
    
    # Set up console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Create audit logger
    audit_logger = logging.getLogger('audit')
    audit_file = f"{log_dir}/{service_name}_audit.log"
    audit_handler = logging.handlers.RotatingFileHandler(
        audit_file,
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    audit_handler.setFormatter(log_format)
    audit_logger.addHandler(audit_handler)
    audit_logger.setLevel(logging.INFO)
    
    return root_logger, audit_logger

def log_audit_event(
    event_type: str,
    user_id: str,
    action: str,
    resource: str,
    status: str,
    details: dict = None
):
    """Log an audit event"""
    audit_logger = logging.getLogger('audit')
    
    event = {
        'timestamp': datetime.utcnow().isoformat(),
        'event_type': event_type,
        'user_id': user_id,
        'action': action,
        'resource': resource,
        'status': status,
        'details': details or {}
    }
    
    audit_logger.info(f"AUDIT: {event}") 