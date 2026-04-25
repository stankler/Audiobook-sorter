#!/bin/bash
set -e
PLUGIN_UI_DIR=/usr/local/emhttp/plugins/audiobook-organizer

echo "Installing Audiobook Organizer..."

# Build Docker image
echo "Building Docker image (this may take a few minutes)..."
docker build -t audiobook-organizer:latest daemon/

# Copy UI files
mkdir -p $PLUGIN_UI_DIR
cp -r ui/* $PLUGIN_UI_DIR/

# Install rc script
cp plugin/scripts/rc.audiobook-organizer /etc/rc.d/rc.audiobook-organizer
chmod +x /etc/rc.d/rc.audiobook-organizer

# Start daemon
/etc/rc.d/rc.audiobook-organizer start

echo "Installation complete. Visit Tools > Audiobook Organizer in Unraid."
