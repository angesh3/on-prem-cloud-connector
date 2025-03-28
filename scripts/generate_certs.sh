#!/bin/bash

# Create directories
mkdir -p certs
cd certs

# Generate CA private key and certificate
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 1024 -out ca.crt \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=Test CA"

# Generate device private key and CSR
openssl genrsa -out device.key 2048
openssl req -new -key device.key -out device.csr \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=device001"

# Sign device certificate with CA
openssl x509 -req -in device.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out device.crt -days 365 -sha256

# Clean up CSR
rm device.csr

# Set appropriate permissions
chmod 600 *.key
chmod 644 *.crt

echo "Certificates generated successfully in ./certs directory" 