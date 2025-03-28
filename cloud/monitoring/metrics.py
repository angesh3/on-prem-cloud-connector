from prometheus_client import Counter, Histogram, Gauge
import time
from functools import wraps
from typing import Callable
import logging

# Initialize metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint']
)

ACTIVE_CONNECTIONS = Gauge(
    'active_connections',
    'Number of currently active connections'
)

DEVICE_COUNT = Gauge(
    'registered_devices_total',
    'Total number of registered devices'
)

ERROR_COUNT = Counter(
    'error_total',
    'Total number of errors',
    ['type', 'message']
)

def track_request_metrics():
    """Decorator to track request metrics"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            ACTIVE_CONNECTIONS.inc()
            
            try:
                response = await func(*args, **kwargs)
                status = response.status_code
            except Exception as e:
                ERROR_COUNT.labels(
                    type=type(e).__name__,
                    message=str(e)
                ).inc()
                ACTIVE_CONNECTIONS.dec()
                raise
            finally:
                duration = time.time() - start_time
                REQUEST_LATENCY.labels(
                    method=kwargs.get('method', 'UNKNOWN'),
                    endpoint=kwargs.get('endpoint', 'UNKNOWN')
                ).observe(duration)
                
                REQUEST_COUNT.labels(
                    method=kwargs.get('method', 'UNKNOWN'),
                    endpoint=kwargs.get('endpoint', 'UNKNOWN'),
                    status=status
                ).inc()
                
                ACTIVE_CONNECTIONS.dec()
            
            return response
        return wrapper
    return decorator

def update_device_count(count: int):
    """Update the total number of registered devices"""
    DEVICE_COUNT.set(count)

def log_error(error_type: str, message: str):
    """Log and track an error"""
    ERROR_COUNT.labels(
        type=error_type,
        message=message
    ).inc()
    logging.error(f"{error_type}: {message}") 