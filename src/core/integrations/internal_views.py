"""
Внутренний HTTP API ModuleBridge (/internal/bridge/*).

Не для браузера: только service-to-service с BRIDGE_INTERNAL_TOKEN.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from src.core.integrations import bridge

logger = logging.getLogger('integrations.bridge.internal')

_TOKEN_HEADER = 'HTTP_X_BRIDGE_TOKEN'


def _token_ok(request: HttpRequest) -> bool:
    expected = (getattr(settings, 'BRIDGE_INTERNAL_TOKEN', '') or '').strip()
    if not expected:
        # В development без токена — только loopback; в prod обязателен токен.
        if getattr(settings, 'DEBUG', False):
            return True
        return False
    got = request.META.get(_TOKEN_HEADER, '') or request.headers.get('X-Bridge-Token', '')
    return got == expected


def _unauthorized() -> JsonResponse:
    return JsonResponse({'detail': 'Unauthorized'}, status=401)


def _json_safe_providers(providers: dict[str, Any]) -> dict[str, Any]:
    """Оставляет только JSON-сериализуемые значения группы."""
    safe: dict[str, Any] = {}
    for key, obj in providers.items():
        try:
            json.dumps(obj, default=None)
        except (TypeError, ValueError):
            # dict с callables — сериализуем без callables
            if isinstance(obj, dict):
                trimmed = {}
                for k, v in obj.items():
                    if callable(v):
                        continue
                    try:
                        json.dumps(v)
                        trimmed[k] = v
                    except (TypeError, ValueError):
                        continue
                safe[key] = trimmed
            continue
        else:
            safe[key] = obj
    return safe


@csrf_exempt
@require_POST
def bridge_call(request: HttpRequest) -> JsonResponse:
    if not _token_ok(request):
        return _unauthorized()
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)

    op = body.get('op')
    if not op or not isinstance(op, str):
        return JsonResponse({'detail': 'op is required'}, status=400)

    args = body.get('args') or []
    kwargs = body.get('kwargs') or {}
    if not isinstance(args, list) or not isinstance(kwargs, dict):
        return JsonResponse({'detail': 'args must be list, kwargs must be object'}, status=400)

    # Только локальный провайдер — иначе цикл remote→remote.
    transport = getattr(bridge, '_transport', None)
    handler = None
    providers = getattr(transport, '_providers', None)
    if isinstance(providers, dict):
        handler = providers.get(op)

    if handler is None:
        return JsonResponse({'detail': f'Provider {op!r} not found locally'}, status=404)

    try:
        result = handler(*args, **kwargs)
    except Exception:
        logger.exception('internal bridge call failed for %s', op)
        return JsonResponse({'detail': 'Handler error'}, status=500)

    try:
        json.dumps(result)
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'Handler result is not JSON-serializable'}, status=500)

    return JsonResponse({'result': result})


@csrf_exempt
@require_GET
def bridge_has(request: HttpRequest) -> JsonResponse:
    if not _token_ok(request):
        return _unauthorized()
    op = request.GET.get('op', '').strip()
    if not op:
        return JsonResponse({'detail': 'op is required'}, status=400)

    transport = getattr(bridge, '_transport', None)
    providers = getattr(transport, '_providers', None)
    has_local = isinstance(providers, dict) and op in providers
    return JsonResponse({'has': bool(has_local)})


@csrf_exempt
@require_GET
def bridge_all(request: HttpRequest) -> JsonResponse:
    if not _token_ok(request):
        return _unauthorized()
    group = request.GET.get('group', '').strip()
    if not group:
        return JsonResponse({'detail': 'group is required'}, status=400)

    transport = getattr(bridge, '_transport', None)
    groups = getattr(transport, '_groups', None)
    local: dict[str, Any] = {}
    if isinstance(groups, dict):
        local = dict(groups.get(group, {}))

    return JsonResponse({'providers': _json_safe_providers(local)})
