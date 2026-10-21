"""
Директория содержащая настройки и конфигурации для Django-API-приложения.
"""

from pathlib import Path
import sys

_project_root = Path(__file__).resolve().parents[4]
_deployment = str(_project_root / 'core' / 'deployment')
if _deployment not in sys.path:
    sys.path.insert(0, _deployment)

from project_isolation import validate_project  # noqa: E402

# До settings/AppConfig: они могут подготавливать схемы БД.
validate_project(_project_root)
