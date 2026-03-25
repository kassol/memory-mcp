#!/bin/bash
# SessionStart hook: inject working memory briefing as context.
# Only fires on fresh startup (not resume/compact).
python3 -c "
import sys, json, subprocess
d = json.load(sys.stdin)
source = d.get('source', '')
if source and source != 'startup':
    sys.exit(0)
r = subprocess.run(['mem', 'wm', '--format', 'text'], capture_output=True, text=True)
if r.returncode == 0:
    print(r.stdout, end='')
else:
    print('Memory service unavailable')
"
