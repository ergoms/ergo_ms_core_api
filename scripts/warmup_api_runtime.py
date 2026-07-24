"""
HTTP-опрос GET /api/system/ready/ после старта API.

Используется оркестрацией (start-all, службы ОС, healthcheck Docker)
и скриптами запуска клиента/nginx — клиент ждёт ready перед Vite/nginx.
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
    # Bind-адрес 0.0.0.0 / :: нельзя использовать как URL для опроса с хоста.
    if host in ('0.0.0.0', '::', '[::]'):
        host = '127.0.0.1'
    port = os.environ.get('API_PORT', '8000').strip() or '8000'
    return f'http://{host}:{port}/api/system/ready/'


def wait_until_api_ready(
    *,
    url: str | None = None,
    timeout_sec: float | None = None,
    interval_sec: float | None = None,
) -> int:
    """Ждёт ready=true. 0 — успех, 1 — таймаут или ERGO_SKIP не задан и API недоступен."""
    if os.environ.get('ERGO_SKIP_API_READY_WAIT', '').strip().lower() in ('1', 'true', 'yes'):
        print(format_console('skip', 'Ожидание API ready пропущено (ERGO_SKIP_API_READY_WAIT)'))
        return 0

    ready_url = (url or os.environ.get('ERGO_READY_URL', _default_ready_url())).strip()
    timeout = float(
        timeout_sec
        if timeout_sec is not None
        else os.environ.get('ERGO_READY_TIMEOUT', '60')
    )
    interval = float(
        interval_sec
        if interval_sec is not None
        else os.environ.get('ERGO_READY_INTERVAL', '0.5')
    )
    deadline = time.monotonic() + timeout

    print(format_console('info', f'Ожидание готовности API: {ready_url}'))
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(ready_url, timeout=2) as response:
                if response.status != 200:
                    time.sleep(interval)
                    continue
                payload = json.loads(response.read().decode('utf-8'))
                if payload.get('ready') is True:
                    print(format_console('ok', f'API готов: {ready_url}'))
                    return 0
        except urllib.error.HTTPError as exc:
            if exc.code != 503:
                pass
        except Exception:
            pass
        time.sleep(interval)

    print(format_console('warning', f'API ready не ответил за {timeout:.0f} с: {ready_url}'))
    return 1


def main() -> int:
    return wait_until_api_ready()


if __name__ == '__main__':
    sys.exit(main())
