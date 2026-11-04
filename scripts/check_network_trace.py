"""Check native-library networking too; Python socket mocks do not cover C/C++."""
from pathlib import Path
import sys

trace = Path(sys.argv[1]).read_text()
assert 'exited with 0' in trace, 'Missing successful traced process exit'
calls = [line for line in trace.splitlines() if 'AF_INET' in line]
if calls:
    raise SystemExit(f'Offline speech attempted {len(calls)} internet socket operations')
print('Native syscall trace: no IPv4/IPv6 socket operations during voice synthesis and shutdown.')
