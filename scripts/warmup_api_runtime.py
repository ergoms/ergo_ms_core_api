"""
HTTP-опрос GET /api/system/ready/ после старта daphne.

Используется оркестрацией (start-all, healthcheck). Не блокирует ergoms dev, если API уже отвечает.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

from _common import format_console


def _default_ready_url() -> str:
    host = os.environ.get('API_HOST', '127.0.0.1').strip() or '127.0.0.1'
    port = os.environ.get('API_PORT', '8000').strip() or '8000'
    return f'http://{host}:{port}/api/system/ready/'


def main() -> int:
    url = os.environ.get('ERGO_READY_URL', _default_ready_url()).strip()
    timeout_sec = float(os.environ.get('ERGO_READY_TIMEOUT', '60'))
    interval_sec = float(os.environ.get('ERGO_READY_INTERVAL', '0.5'))
    deadline = time.monotonic() + timeout_sec

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status != 200:
                    time.sleep(interval_sec)
                    continue
                payload = json.loads(response.read().decode('utf-8'))
                if payload.get('ready') is True:
                    print(format_console('ok', f'API готов: {url}'))
                    return 0
        except urllib.error.HTTPError as exc:
            if exc.code != 503:
                pass
        except Exception:
            pass
        time.sleep(interval_sec)

    print(format_console('warning', f'API ready не ответил за {timeout_sec:.0f} с: {url}'))
    return 1


if __name__ == '__main__':
    sys.exit(main())
