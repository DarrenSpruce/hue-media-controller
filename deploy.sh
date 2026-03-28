#!/bin/bash
# Deploy script - run this on the Raspberry Pi to set up the service
set -e

echo "=== Hue Media Controller - Deploy ==="

# Install Python venv if needed
if ! command -v python3 &> /dev/null; then
    echo "Installing Python 3..."
    sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Install dependencies
echo "Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt

# Copy config if needed
if [ ! -f "config.yaml" ]; then
    echo "Creating config.yaml from template..."
    cp config.yaml.example config.yaml
    echo ""
    echo "⚠️  Please edit config.yaml with your device IPs before starting!"
    echo "   nano config.yaml"
    echo ""
fi

# Install systemd service
echo "Installing systemd service..."
sudo cp hue-media-controller.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hue-media-controller

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Next steps:"
echo "  1. Edit config.yaml with your device IPs"
echo "  2. Run 'source venv/bin/activate && python learn_ir.py' to capture IR codes"
echo "  3. Run 'source venv/bin/activate && python controller.py' for first-time Hue Bridge registration"
echo "  4. Start the service: sudo systemctl start hue-media-controller"
echo ""
