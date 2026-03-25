#!/bin/bash
# SessionStart hook: inject working memory briefing as context.
# Only fires on fresh startup (not resume/compact).
# Passes cwd for project-aware filtering.
python3 -c "
import sys, json, subprocess
d = json.load(sys.stdin)
source = d.get('source', '')
if source and source != 'startup':
    sys.exit(0)
cwd = d.get('cwd', '')
cmd = ['mem', 'wm', '--format', 'text']
if cwd:
    cmd.extend(['--cwd', cwd])
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode == 0 and r.stdout.strip():
    print(r.stdout, end='')
"
