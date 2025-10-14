"""
Файл с вспомогательными методами.

Этот файл содержит различные вспомогательные методы, которые используются в других частях модуля и приложения.
"""

from typing import Dict

from django.core.mail import send_mail
from django.conf import settings

def parse_errors_to_dict(error_dict: Dict[str, list]) -> Dict[str, str]:
    """
    Преобразует словарь ошибок в строковый формат.

    Аргументы:
        error_dict (Dict[str, list]): Словарь, где ключи - это поля, а значения - списки ошибок.

    Возвращает:
        Dict[str, str]: Словарь, где ключи - это поля, а значения - строки, содержащие ошибки, разделенные запятыми.
    """
    parsed_errors = {}

    for field, details in error_dict.items():
        parsed_errors[field] = ", ".join(str(detail) for detail in details)
        
    return parsed_errors

def send_confirmation_email(email: str, code: str) -> None:
    """
    Отправляет email с кодом подтверждения.

    Аргументы:
        email (str): Email адрес получателя.
        code (str): Код подтверждения.

    Возвращает:
        None
    """
    default_from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)

    subject = "Код подтверждения ERGO MS"
    message = f"Ваш код подтверждения: {code}"
    from_email = default_from_email
    recipient_list = [email]

    send_mail(subject,
              message, 
              from_email, 
              recipient_list, 
              fail_silently=False)
    
def convert_snake_to_camel(snake_text: str) -> str:
    """
    Преобразует строку в формате snake_case в CamelCase.

    Формирует строку в формате CamelCase, разделяя исходную строку по символам подчёркивания,
    преобразуя каждую часть в капитализированный формат и объединяя их.

    Аргументы:
        snake_str (str): Строка в формате snake_case для преобразования.

    Возвращает:
        str: Строка в формате CamelCase.
    """
    # Разделяем строку по символу подчеркивания, капитализируем каждую часть и объединяем их
    return ''.join(word.capitalize() for word in snake_text.split('_'))

def convert_path_to_dot_notation(path) -> str:
    """
    Преобразует путь из формата Path в формат с точками.

    Преобразует строку пути, заменяя разделители путей (слэши) на точки.
    Например: 'src/core' -> 'src.core'

    Аргументы:
        path: Путь для преобразования (str или Path).

    Возвращает:
        str: Путь в формате с точками.
    """
    # Преобразуем в строку, если это объект Path
    path_str = str(path)
    # Заменяем слэши на точки и убираем лишние точки
    return path_str.replace('/', '.').replace('\\', '.').strip('.')