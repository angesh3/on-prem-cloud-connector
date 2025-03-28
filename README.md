# On-Premises to Cloud Integration System

This project implements a secure integration system between on-premises environments and cloud-hosted services, supporting large API payloads (up to 2GB) through streaming/chunked transfers.

## Features

- Secure device registration and token-based authentication
- Mutual TLS for secure communication
- Support for large API payloads (up to 2GB) without cloud storage
- Streaming/chunked data transfer
- Real-time data publishing
- Secure API forwarding
- Web-based device management UI

## Architecture

The system consists of the following components:

1. **Cloud Components**:
   - Device Registry & Token Manager
   - Reverse Proxy for API forwarding
   - Pub/Sub system for data streaming

2. **On-Premises Components**:
   - On-Premises Connector/Agent
   - Local Application/API
   - Device Management UI

## Prerequisites

- Docker and Docker Compose
- OpenSSL for certificate generation
- Python 3.9 or higher (for local development)

## Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd <repository-name>
   ```

2. Generate certificates for testing:
   ```bash
   chmod +x scripts/generate_certs.sh
   ./scripts/generate_certs.sh
   ```

3. Create a `.env` file:
   ```bash
   JWT_SECRET_KEY=your-secret-key
   DEVICE_ID=device001
   ```

4. Build and start the services:
   ```bash
   docker-compose up --build
   ```

5. Access the Device Management UI:
   - Open your browser and navigate to `http://localhost:8080`
   - The UI provides:
     - Device registration interface
     - Real-time device status monitoring
     - Connection status tracking
     - Registration information display

## Usage

### 1. Device Registration (Web UI)

1. Open `http://localhost:8080` in your browser
2. Fill in the device registration form:
   - Device ID
   - Metadata (JSON format)
3. Click "Register Device"
4. Monitor the device status in real-time

### 2. Device Registration (API)

The on-premises connector automatically registers with the cloud service on startup. You can also manually register a device:

```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"device_id": "device001", "metadata": {"url": "http://localhost:8080"}}'
```

### 3. Publishing Data

From the on-premises environment:

```python
from onprem.connector.agent import OnPremConnector

connector = OnPremConnector(
    device_id="device001",
    cloud_url="https://cloud-server.example.com",
    cert_path="./certs/device.crt",
    key_path="./certs/device.key"
)

# Publish data
await connector.publish_data({
    "timestamp": "2024-01-01T00:00:00Z",
    "measurements": [...]
})
```

### 4. API Invocation

From the cloud to on-premises:

```bash
curl -X POST http://localhost:8001/forward/device001/api/endpoint \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```

## Security

1. **Authentication**:
   - JWT-based token authentication
   - Token expiration and renewal
   - Device registration validation

2. **Transport Security**:
   - Mutual TLS authentication
   - Certificate-based device validation
   - Encrypted communication

3. **Data Integrity**:
   - Checksum validation for chunked transfers
   - Request/response validation
   - Error handling and retry mechanisms

## Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run tests:
   ```bash
   pytest tests/
   ```

3. Format code:
   ```bash
   black .
   isort .
   ```

## Configuration

### Environment Variables

- `JWT_SECRET_KEY`: Secret key for JWT token generation
- `DEVICE_ID`: Unique identifier for the on-premises device
- `CA_CERT_PATH`: Path to CA certificate
- `CERT_PATH`: Path to device certificate
- `KEY_PATH`: Path to device private key

### Network Configuration

- Registry Service: Port 8000
- Reverse Proxy: Port 8001
- Device Management UI: Port 8080
- On-Premises Connector: Internal network only

#### local run

docker compose down && docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d --build

Main Services:
Device UI: http://localhost:8080
Cloud UI: http://localhost:8003
Registry: http://localhost:8000
Reverse Proxy: http://localhost:8001
On-Prem Connector (internal)
Monitoring Stack:
Grafana: http://localhost:3000 (login with admin/admin)
Prometheus: http://localhost:9090
Loki: http://localhost:3100 (used internally by Grafana)
To access the monitoring dashboards:
Open Grafana at http://localhost:3000
Log in with:
Username: admin
Password: admin
You'll be prompted to change the password on first login
The monitoring stack is collecting metrics from all services, and you can:
View service metrics in Prometheus
Create custom dashboards in Grafana
View logs centrally through Loki in Grafana

## Troubleshooting

1. **Certificate Issues**:
   - Ensure certificates are generated correctly
   - Check certificate permissions
   - Verify CA trust chain

2. **Connection Issues**:
   - Check network connectivity
   - Verify firewall settings
   - Ensure correct URLs in configuration

3. **Large Payload Issues**:
   - Monitor memory usage
   - Check network timeout settings
   - Verify chunked transfer encoding

4. **UI Issues**:
   - Clear browser cache
   - Check browser console for errors
   - Verify network connectivity to services

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 
