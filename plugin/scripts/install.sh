#!/bin/bash
set -e
DAEMON_DIR=/usr/local/lib/audiobook-organizer-daemon
PLUGIN_UI_DIR=/usr/local/emhttp/plugins/audiobook-organizer

echo "Installing Audiobook Organizer..."

mkdir -p $DAEMON_DIR
cp -r daemon/* $DAEMON_DIR/

python3 -m venv $DAEMON_DIR/venv
$DAEMON_DIR/venv/bin/pip install --quiet \
  --trusted-host pypi.org \
  --trusted-host files.pythonhosted.org \
  -r $DAEMON_DIR/requirements.txt

mkdir -p $PLUGIN_UI_DIR
cp -r ui/* $PLUGIN_UI_DIR/

cp plugin/scripts/rc.audiobook-organizer /etc/rc.d/rc.audiobook-organizer
chmod +x /etc/rc.d/rc.audiobook-organizer

/etc/rc.d/rc.audiobook-organizer start

echo "Installation complete. Visit Tools > Audiobook Organizer in Unraid."
