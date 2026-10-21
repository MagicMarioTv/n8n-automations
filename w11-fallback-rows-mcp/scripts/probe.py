"""Named checks against the W11 MCP endpoint. Writes a JSON record and prints a summary.

Usage: python3 -I probe.py <base_url> <token_file> <out_file>
The token is read from a file and never written to the record.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE, TOKEN_FILE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
URL = BASE.rstrip('/') + '/mcp/fallback-rows'
TOKEN = open(TOKEN_FILE).read().strip()
PROPOSED = '2025-11-25'


def post(body, token=TOKEN, session=None):
    headers = {'content-type': 'application/json', 'accept': 'application/json, text/event-stream'}
    if token:
        headers['authorization'] = f'Bearer {token}'
    if session:
        headers['mcp-session-id'] = session
        headers['mcp-protocol-version'] = PROPOSED
    req = urllib.request.Request(URL, method='POST', data=json.dumps(body).encode(), headers=headers)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req) as r:
            status, hdrs, raw = r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        status, hdrs, raw = e.code, dict(e.headers), e.read().decode()
    ms = round((time.monotonic() - t0) * 1000)
    # Streamable HTTP may answer as JSON or as one SSE event; keep the JSON-RPC message either way.
    msg = None
    if raw.strip():
        if 'text/event-stream' in hdrs.get('Content-Type', hdrs.get('content-type', '')):
            data = [l[5:].strip() for l in raw.splitlines() if l.startswith('data:')]
            msg = json.loads(data[-1]) if data else None
        else:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                msg = raw
    lower = {k.lower(): v for k, v in hdrs.items()}
    return status, lower, msg, ms


record = {'endpoint': URL, 'checks': []}


def check(name, expect, status, msg, ms, **extra):
    entry = {'check': name, 'expect': expect, 'http_status': status, 'ms': ms, **extra, 'response': msg}
    record['checks'].append(entry)
    return entry


# Auth
s, h, m, ms = post({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}, token=None)
check('no token', '403', s, m, ms)
s, h, m, ms = post({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}, token='wrong' * 8)
check('wrong token', '403', s, m, ms)

# Session
s, h, m, ms = post({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
    'protocolVersion': PROPOSED, 'capabilities': {}, 'clientInfo': {'name': 'w11-probe', 'version': '1'}}})
session = h.get('mcp-session-id')
check('initialize', f'200, protocolVersion {PROPOSED}, a session ID', s, m, ms, session_id_present=bool(session))
post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, session=session)

s, h, m, ms = post({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}, session=session)
check('tools/list', 'three tools: list_fallback_rows, get_fallback_row, get_status_vocabulary', s, m, ms)

calls = [
    ('list, no arguments', 'list_fallback_rows', {}, 'total 12, returned 12, oldest first'),
    ('list, platform Max', 'list_fallback_rows', {'platform': 'Max'}, 'Max rows only'),
    ('list, limit 3', 'list_fallback_rows', {'limit': 3}, 'total 12, returned 3, the three oldest'),
    ('list, unknown platform', 'list_fallback_rows', {'platform': 'Netflix'}, 'error field naming the allowed platforms'),
    ('list, limit 0', 'list_fallback_rows', {'limit': 0}, 'error field, limit 1 to 50'),
    ('list, limit 51', 'list_fallback_rows', {'limit': 51}, 'error field, limit 1 to 50'),
    ('get, FB-1011', 'get_fallback_row', {'row_id': 'FB-1011'}, 'the row, with source and last_note'),
    ('get, lower case fb-1004', 'get_fallback_row', {'row_id': 'fb-1004'}, 'the row FB-1004'),
    ('get, FB-9999', 'get_fallback_row', {'row_id': 'FB-9999'}, 'error field: row not found'),
    ('get, malformed 1004', 'get_fallback_row', {'row_id': '1004'}, 'error field: must look like FB-NNNN'),
    ('get, no row_id', 'get_fallback_row', {}, 'an error, not a row'),
    ('vocabulary, no arguments', 'get_status_vocabulary', {}, 'total 10, every status with its meaning'),
    ('vocabulary, QC_Hold', 'get_status_vocabulary', {'status': ' QC_Hold '}, 'the qc_hold entry: case and spaces ignored'),
    ('vocabulary, unknown status', 'get_status_vocabulary', {'status': 'in_progress'}, 'error field listing the known names'),
]
for i, (name, tool, args, expect) in enumerate(calls, start=10):
    s, h, m, ms = post({'jsonrpc': '2.0', 'id': i, 'method': 'tools/call',
                        'params': {'name': tool, 'arguments': args}}, session=session)
    check(name, expect, s, m, ms, tool=tool, arguments=args)

with open(OUT, 'w') as f:
    json.dump(record, f, indent=2)
    f.write('\n')
for c in record['checks']:
    r = c['response']
    brief = json.dumps(r)[:160] if r is not None else ''
    print(f"{c['check']:<26} {c['http_status']} {c['ms']:>5}ms  {brief}")
