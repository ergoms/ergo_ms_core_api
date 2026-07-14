"""
Прогрев кэшей только при необходимости.

Проверяет celery_queues.bin / celery_routes_queues.bin без Django.
Если кэш валиден — выход за миллисекунды. Иначе — вызывает warmup_caches (Django).
"""

import logging
import os
import subprocess
import sys

from _common import API_DIR, PROJECT_ROOT, cache_valid

_DEPLOYMENT_SCRIPTS = PROJECT_ROOT / 'core' / 'deployment' / 'scripts'
if str(_DEPLOYMENT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_DEPLOYMENT_SCRIPTS))

from ensure_redis_if_enabled import ensure_redis_for_dev  # noqa: E402


logger = logging.getLogger('core.utils.warmup')


def main() -> int:
    """
    Точка входа скрипта warmup_caches_if_needed.

    Сценарии:
      - REDIS_ENABLED=true -> запускаем Redis до прогрева (API и кэши зависят от него);
      - кэш валиден -> выходим сразу (warmup пропускается);
      - кэш невалиден -> вызываем Django-команду warmup_caches для прогрева.
    """
    redis_code = ensure_redis_for_dev(quiet=True)
    if redis_code != 0:
        logger.warning('warmup_caches_if_needed: не удалось запустить Redis (код %s)', redis_code)
        return redis_code

    if cache_valid():
        logger.info('warmup_caches_if_needed: кэш уже валиден, Django warmup не требуется')
        return 0

    logger.info('warmup_caches_if_needed: кэш невалиден, запускаем Django команду warmup_caches')
    result = subprocess.run(
        [sys.executable, '-m', 'commands', 'warmup_caches'],
        cwd=str(API_DIR),
        timeout=180,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'},
    )
    if result.returncode == 0:
        logger.info('warmup_caches_if_needed: warmup_caches завершилась успешно')
    else:
        logger.warning('warmup_caches_if_needed: warmup_caches завершилась с кодом %s', result.returncode)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
