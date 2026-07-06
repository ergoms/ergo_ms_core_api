from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

TopicAuthFn = Callable[[Any, dict[str, str]], bool]
GroupResolverFn = Callable[[Any, dict[str, str]], str | None]


@dataclass(frozen=True)
class RealtimeTopicRegistration:
    pattern: str
    authorize: TopicAuthFn
    resolve_group: GroupResolverFn


_REGISTRY: list[RealtimeTopicRegistration] = []
_PATTERN_CACHE: list[tuple[re.Pattern[str], RealtimeTopicRegistration]] | None = None


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    result = ['^']
    i = 0
    while i < len(pattern):
        if pattern[i] == '{':
            end = pattern.index('}', i)
            name = pattern[i + 1:end]
            result.append(f'(?P<{name}>[^:]+)')
            i = end + 1
        else:
            end = pattern.find('{', i)
            chunk = pattern[i:] if end == -1 else pattern[i:end]
            result.append(re.escape(chunk))
            i = len(pattern) if end == -1 else end
    result.append('$')
    return re.compile(''.join(result))


def _compile_patterns() -> list[tuple[re.Pattern[str], RealtimeTopicRegistration]]:
    global _PATTERN_CACHE
    if _PATTERN_CACHE is None:
        _PATTERN_CACHE = [( _pattern_to_regex(reg.pattern), reg) for reg in _REGISTRY]
    return _PATTERN_CACHE


def register_realtime_topic(
    pattern: str,
    *,
    authorize: TopicAuthFn,
    resolve_group: GroupResolverFn,
) -> None:
    """Регистрация topic модуля: pattern вида ``bi:dashboard:{public_id}``."""
    _REGISTRY.append(RealtimeTopicRegistration(pattern, authorize, resolve_group))
    global _PATTERN_CACHE
    _PATTERN_CACHE = None


def match_registered_topic(topic: str) -> tuple[RealtimeTopicRegistration, dict[str, str]] | None:
    for regex, reg in _compile_patterns():
        match = regex.match(topic)
        if match:
            return reg, match.groupdict()
    return None


def authorize_registered_topic(user, topic: str) -> str | None:
    matched = match_registered_topic(topic)
    if matched is None:
        return None
    reg, params = matched
    if not reg.authorize(user, params):
        return None
    return reg.resolve_group(user, params)
