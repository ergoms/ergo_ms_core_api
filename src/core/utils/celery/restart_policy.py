"""Что делать с задачей модуля, которую оборвал перезапуск воркера.

Политику задаёт hook-файл ``modules/<name>/task_restart.yaml``. Без файла
действует ``CELERY_RESTART_POLICY`` (по умолчанию ``hold``). Задачи ядра
(не ``modules.<name>.*``) по-прежнему выполняются заново.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger('celery.restart')

RESTART_POLICY_FILENAME = 'task_restart.yaml'

# Не запускать, сохранить и ждать ergoms celery-parked --resume.
HOLD = 'hold'
# Не запускать и не хранить: периодическую задачу Beat поставит сам.
DROP = 'drop'
# Выполнить заново сразу, как было до политики.
REQUEUE = 'requeue'
ACTIONS = (HOLD, DROP, REQUEUE)

DEFAULT_RESUME_KWARG = 'resume'
_MODULE_PREFIX = 'modules.'


@dataclass(frozen=True)
class RestartRule:
    pattern: str
    action: str
    resume_kwarg: str | None


@dataclass(frozen=True)
class ModuleRestartPolicy:
    default: str
    resume_kwarg: str | None
    rules: tuple[RestartRule, ...]


@dataclass(frozen=True)
class RestartDecision:
    action: str
    resume_kwarg: str | None
    module: str | None


def _modules_dir() -> Path:
    from src.config.paths import MODULES_DIR

    return MODULES_DIR


def _env_default() -> str:
    raw = (os.environ.get('CELERY_RESTART_POLICY') or HOLD).strip().lower()
    return raw if raw in ACTIONS else HOLD


def module_of_task(task_name: str) -> str | None:
    if not task_name or not task_name.startswith(_MODULE_PREFIX):
        return None
    parts = task_name.split('.')
    return parts[1] if len(parts) > 2 and parts[1] else None


def _action(value, fallback: str, where: str) -> str:
    if value is None or value == '':
        return fallback
    text = str(value).strip().lower()
    if text in ACTIONS:
        return text
    logger.warning('%s: неизвестное значение on_restart=%r, беру %s', where, value, fallback)
    return fallback


def _resume_kwarg(raw: dict, fallback: str | None) -> str | None:
    if 'resume_kwarg' not in raw:
        return fallback
    value = raw.get('resume_kwarg')
    # resume_kwarg: null — задача продолжает сама, флаг не передаём.
    return str(value).strip() or None if value else None


def parse_policy(data, *, env_default: str, where: str = RESTART_POLICY_FILENAME) -> ModuleRestartPolicy:
    """Разбор содержимого task_restart.yaml. Пустой или битый файл — политика по умолчанию."""
    if not isinstance(data, dict):
        return ModuleRestartPolicy(env_default, DEFAULT_RESUME_KWARG, ())
    default = _action(data.get('default'), env_default, where)
    resume_kwarg = _resume_kwarg(data, DEFAULT_RESUME_KWARG)
    rules: list[RestartRule] = []
    for item in data.get('tasks') or []:
        if not isinstance(item, dict):
            continue
        pattern = str(item.get('pattern') or '').strip()
        if not pattern:
            continue
        rules.append(
            RestartRule(
                pattern=pattern,
                action=_action(item.get('on_restart'), default, f'{where}: {pattern}'),
                resume_kwarg=_resume_kwarg(item, resume_kwarg),
            )
        )
    return ModuleRestartPolicy(default, resume_kwarg, tuple(rules))


@lru_cache(maxsize=None)
def load_module_policy(module: str) -> ModuleRestartPolicy:
    env_default = _env_default()
    path = _modules_dir() / module / RESTART_POLICY_FILENAME
    if not path.is_file():
        return ModuleRestartPolicy(env_default, DEFAULT_RESUME_KWARG, ())
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except Exception as exc:
        logger.warning('%s не прочитан (%s), беру политику по умолчанию', path, exc)
        data = None
    return parse_policy(data, env_default=env_default, where=str(path))


def decide_for(policy: ModuleRestartPolicy, task_name: str, module: str | None) -> RestartDecision:
    """Первое совпавшее правило сверху вниз, иначе default модуля."""
    for rule in policy.rules:
        if fnmatch.fnmatchcase(task_name, rule.pattern):
            return RestartDecision(rule.action, rule.resume_kwarg, module)
    return RestartDecision(policy.default, policy.resume_kwarg, module)


def decide(task_name: str) -> RestartDecision:
    module = module_of_task(task_name)
    if module is None:
        return RestartDecision(REQUEUE, None, None)
    return decide_for(load_module_policy(module), task_name, module)
