"""Валидация навигации в уведомлениях (запрет pk в URL и route.params)."""

from __future__ import annotations

import re
import uuid

_NUMERIC_PATH_SEGMENT = re.compile(r'/(?:\d+)(?:/|$|\?)')


def _is_numeric_ref(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return bool(stripped) and stripped.isdigit()
    return False


def _is_uuid_ref(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def validate_notification_navigation(
    *,
    link_url: str | None = None,
    route: dict | None = None,
) -> list[str]:
    """Возвращает список ошибок; пустой список — навигация допустима."""
    errors: list[str] = []

    if link_url:
        url = str(link_url).strip()
        if url:
            if re.match(r'^https?://', url, re.IGNORECASE):
                errors.append('link_url: внешние абсолютные URL запрещены')
            elif _NUMERIC_PATH_SEGMENT.search(url.split('#')[0]):
                errors.append('link_url: числовые сегменты пути запрещены — используйте public_id')

    if route is not None:
        if not isinstance(route, dict):
            errors.append('route: ожидается объект {name, params}')
        else:
            params = route.get('params')
            if params is not None and not isinstance(params, dict):
                errors.append('route.params: ожидается объект')
            elif isinstance(params, dict):
                for key, value in params.items():
                    if _is_numeric_ref(value):
                        errors.append(
                            f'route.params.{key}: используйте public_id (UUID), не числовой pk',
                        )
                    elif isinstance(value, str) and value.strip() and not _is_uuid_ref(value):
                        # Именованные строковые параметры (slug, tab) допустимы; чисто числовые — нет
                        if value.strip().isdigit():
                            errors.append(
                                f'route.params.{key}: используйте public_id (UUID), не числовой pk',
                            )

    return errors


def sanitize_notification_navigation(
    *,
    link_url: str | None = None,
    route: dict | None = None,
) -> tuple[str | None, dict | None]:
    """Очищает недопустимую навигацию; возвращает (link_url, route)."""
    errors = validate_notification_navigation(link_url=link_url, route=route)
    if not errors:
        return link_url, route

    safe_link = link_url
    safe_route = route
    if link_url and any('link_url' in item for item in errors):
        safe_link = None
    if route is not None and any(item.startswith('route') for item in errors):
        safe_route = None
    return safe_link, safe_route
