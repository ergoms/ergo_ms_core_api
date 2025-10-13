"""
Точка входа для выполнения Django команд через Poetry.
"""

import sys
import logging

from typing import Dict, Type

from commands.base import PoetryCommand
from commands.discovery import discovery

from src.config.settings.logger import LOGGING

# Настройка логгера
logger = logging.getLogger('commands')
formatter = logging.Formatter(
    fmt=LOGGING['formatters']['simple']['format'],
    style=LOGGING['formatters']['simple']['style']
)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.setLevel(logging.INFO)


def get_commands() -> Dict[str, Type[PoetryCommand]]:
    """Получение всех доступных команд."""
    try:
        return discovery.get_all()
    except Exception as e:
        logger.warning(f"Ошибка при загрузке команд: {e}")
        return {}


def main():
    """Главная функция."""
    commands = get_commands()

    if len(sys.argv) < 2:
        logger.info("Использование: api <команда> [аргументы...]")
        logger.info("Доступные команды: %s", ", ".join(sorted(commands.keys())))
        return

    command_name = sys.argv[1]
    args = sys.argv[2:]

    command_class = commands.get(command_name)
    if not command_class:
        logger.error("Неизвестная команда: %s", command_name)
        logger.info("Доступные команды: %s", ", ".join(sorted(commands.keys())))
        return

    try:
        command_instance = command_class()
        exit_code = command_instance.run(*args)
        sys.exit(exit_code if exit_code is not None else 0)
    except Exception as e:
        logger.error("Ошибка при выполнении команды %s: %s", command_name, e)
        sys.exit(1)


if __name__ == "__main__":
    main()