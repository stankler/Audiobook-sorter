#!/bin/bash
/etc/rc.d/rc.audiobook-organizer stop 2>/dev/null || true
rm -rf /usr/local/lib/audiobook-organizer-daemon
rm -rf /usr/local/emhttp/plugins/audiobook-organizer
rm -f /etc/rc.d/rc.audiobook-organizer
echo "Audiobook Organizer removed. Config preserved at /boot/config/plugins/audiobook-organizer/"
