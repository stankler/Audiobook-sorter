#!/bin/bash
# Called by the .plg post-install block — not used directly in normal installs.
# Kept for manual/development installs.
set -e

IMAGE="ghcr.io/stankler/audiobook-organizer:latest"
PLUGIN_UI_DIR=/usr/local/emhttp/plugins/audiobook-organizer

echo "Installing Audiobook Organizer..."

mkdir -p $PLUGIN_UI_DIR/js $PLUGIN_UI_DIR/css $PLUGIN_UI_DIR/include
cp ui/AudiobookOrganizer.page $PLUGIN_UI_DIR/
cp ui/api.php                 $PLUGIN_UI_DIR/
cp ui/js/app.js               $PLUGIN_UI_DIR/js/
cp ui/css/style.css           $PLUGIN_UI_DIR/css/
cp ui/include/api_client.php  $PLUGIN_UI_DIR/include/

cp plugin/scripts/rc.audiobook-organizer /etc/rc.d/rc.audiobook-organizer
chmod +x /etc/rc.d/rc.audiobook-organizer

echo "Pulling Docker image ${IMAGE}..."
docker pull "${IMAGE}"

/etc/rc.d/rc.audiobook-organizer start
echo "Done. Open Tools > Audiobook Organizer."
