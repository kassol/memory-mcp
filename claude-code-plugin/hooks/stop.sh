#!/bin/bash
# Stop hook: extract memories from conversation transcript.
# Runs with async: true (fire-and-forget).
python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('stop_hook_active'):
    sys.exit(0)
tp = d.get('transcript_path', '')
if not tp:
    sys.exit(0)
import subprocess
subprocess.run(['mem', 'extract', '--transcript', tp], stderr=subprocess.DEVNULL)
"
