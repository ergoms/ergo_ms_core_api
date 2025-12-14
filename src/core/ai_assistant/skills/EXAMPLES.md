# Примеры навыков для AI ассистента

## Пример 1: Навык для работы с файлами

```python
from src.core.ai_assistant.skills import BaseSkill, SkillResult
from typing import Any, Dict, Optional
import os

class FileOperationsSkill(BaseSkill):
    """Навык для работы с файлами."""
    
    @property
    def name(self) -> str:
        return "file_operations"
    
    @property
    def description(self) -> str:
        return "Выполняет операции с файлами: чтение, запись, удаление"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "write", "delete"],
                    "description": "Тип операции"
                },
                "file_path": {
                    "type": "string",
                    "description": "Путь к файлу"
                },
                "content": {
                    "type": "string",
                    "description": "Содержимое для записи (только для write)"
                }
            },
            "required": ["operation", "file_path"]
        }
    
    def can_handle(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        keywords = ['прочитай файл', 'запиши в файл', 'удали файл', 'read file', 'write file']
        return any(kw in query.lower() for kw in keywords)
    
    def execute(self, query: str, parameters: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        if not parameters:
            return SkillResult(success=False, error="Не указаны параметры")
        
        operation = parameters.get('operation')
        file_path = parameters.get('file_path')
        
        try:
            if operation == 'read':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return SkillResult(success=True, result=f"Содержимое файла:\n{content}")
            
            elif operation == 'write':
                content = parameters.get('content', '')
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return SkillResult(success=True, result=f"Файл {file_path} успешно записан")
            
            elif operation == 'delete':
                if os.path.exists(file_path):
                    os.remove(file_path)
                    return SkillResult(success=True, result=f"Файл {file_path} удален")
                else:
                    return SkillResult(success=False, error=f"Файл {file_path} не найден")
            
            else:
                return SkillResult(success=False, error=f"Неизвестная операция: {operation}")
        
        except Exception as e:
            return SkillResult(success=False, error=f"Ошибка: {str(e)}")
```

## Пример 2: Навык для работы с API

```python
from src.core.ai_assistant.skills import BaseSkill, SkillResult
from typing import Any, Dict, Optional
import requests

class APICallSkill(BaseSkill):
    """Навык для выполнения HTTP запросов."""
    
    @property
    def name(self) -> str:
        return "api_call"
    
    @property
    def description(self) -> str:
        return "Выполняет HTTP запросы к внешним API"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL для запроса"
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "default": "GET",
                    "description": "HTTP метод"
                },
                "data": {
                    "type": "object",
                    "description": "Данные для отправки (для POST/PUT)"
                }
            },
            "required": ["url"]
        }
    
    def can_handle(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        return any(kw in query.lower() for kw in ['вызови api', 'сделай запрос', 'call api', 'http request'])
    
    def execute(self, query: str, parameters: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        if not parameters:
            return SkillResult(success=False, error="Не указаны параметры")
        
        url = parameters.get('url')
        method = parameters.get('method', 'GET')
        data = parameters.get('data')
        
        try:
            if method == 'GET':
                response = requests.get(url)
            elif method == 'POST':
                response = requests.post(url, json=data)
            elif method == 'PUT':
                response = requests.put(url, json=data)
            elif method == 'DELETE':
                response = requests.delete(url)
            else:
                return SkillResult(success=False, error=f"Неизвестный метод: {method}")
            
            response.raise_for_status()
            return SkillResult(
                success=True,
                result=f"Ответ API ({response.status_code}):\n{response.text[:1000]}",
                metadata={'status_code': response.status_code}
            )
        except Exception as e:
            return SkillResult(success=False, error=f"Ошибка API запроса: {str(e)}")
```

## Регистрация навыка

Поместите файл навыка в `core/api/src/core/ai_assistant/skills/builtin/` - он будет автоматически обнаружен.

Или зарегистрируйте вручную:

```python
from src.core.ai_assistant.skills import SkillRegistry
from .my_skill import MySkill

SkillRegistry.register(MySkill())
```

