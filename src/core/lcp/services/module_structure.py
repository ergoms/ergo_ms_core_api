"""
Сервис для создания структуры модуля LCP в файловой системе.
"""

import os
from pathlib import Path
from typing import Optional
import logging

from src.config.settings.base import MODULES_DIR

logger = logging.getLogger(__name__)


class ModuleStructureService:
    """Сервис для создания структуры модуля"""
    
    def __init__(self):
        self.modules_dir = MODULES_DIR
    
    def create_module_structure(self, slug: str, name: str, description: str = '') -> dict:
        """
        Создает полную структуру модуля в файловой системе.
        
        Args:
            slug: Slug модуля (имя папки)
            name: Название модуля
            description: Описание модуля
            
        Returns:
            dict: Результат создания с информацией о созданных файлах и ошибках
        """
        result = {
            'success': False,
            'module_path': None,
            'created_files': [],
            'errors': []
        }
        
        try:
            # Путь к модулю
            module_path = self.modules_dir / slug
            
            # Проверяем, не существует ли уже модуль
            if module_path.exists():
                result['errors'].append(f'Модуль {slug} уже существует')
                return result
            
            # Создаем структуру
            self._create_api_structure(module_path, slug, name, description, result)
            self._create_client_structure(module_path, slug, name, result)
            self._create_env_file(module_path, result)
            
            result['success'] = True
            result['module_path'] = str(module_path)
            logger.info(f'Структура модуля {slug} успешно создана в {module_path}')
            
        except Exception as e:
            error_msg = f'Ошибка при создании структуры модуля {slug}: {str(e)}'
            logger.error(error_msg, exc_info=True)
            result['errors'].append(error_msg)
        
        return result
    
    def _create_api_structure(self, module_path: Path, slug: str, name: str, description: str, result: dict):
        """Создает структуру API модуля"""
        api_path = module_path / 'api'
        api_path.mkdir(parents=True, exist_ok=True)
        
        # __init__.py
        init_file = api_path / '__init__.py'
        init_file.write_text('', encoding='utf-8')
        result['created_files'].append(str(init_file))
        
        # apps.py
        apps_content = f'''"""
Конфигурация приложения для модуля {name}.
"""

from django.apps import AppConfig


class {self._to_class_name(slug)}Config(AppConfig):
    """Конфигурация модуля {name}"""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.modules.{slug}'
    verbose_name = '{name}'
    
    def ready(self):
        """Инициализация модуля при загрузке"""
        pass
'''
        apps_file = api_path / 'apps.py'
        apps_file.write_text(apps_content, encoding='utf-8')
        result['created_files'].append(str(apps_file))
        
        # models.py
        models_content = '''"""
Модели модуля.
"""

from django.db import models


# Добавьте ваши модели здесь
'''
        models_file = api_path / 'models.py'
        models_file.write_text(models_content, encoding='utf-8')
        result['created_files'].append(str(models_file))
        
        # urls.py
        urls_content = f'''"""
URL конфигурация модуля {name}.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

# from . import views

# router = DefaultRouter()
# router.register(r'example', views.ExampleViewSet, basename='example')

urlpatterns = [
    # router.urls,
]
'''
        urls_file = api_path / 'urls.py'
        urls_file.write_text(urls_content, encoding='utf-8')
        result['created_files'].append(str(urls_file))
        
        # views.py
        views_content = f'''"""
ViewSet'ы для модуля {name}.
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

# from .models import YourModel
# from .serializers import YourModelSerializer


# class YourViewSet(viewsets.ModelViewSet):
#     """ViewSet для работы с моделью"""
#     queryset = YourModel.objects.all()
#     serializer_class = YourModelSerializer
#     permission_classes = [IsAuthenticated]
'''
        views_file = api_path / 'views.py'
        views_file.write_text(views_content, encoding='utf-8')
        result['created_files'].append(str(views_file))
        
        # serializers.py
        serializers_content = '''"""
Сериализаторы для модуля.
"""

from rest_framework import serializers

# from .models import YourModel


# class YourModelSerializer(serializers.ModelSerializer):
#     """Сериализатор для модели"""
#     
#     class Meta:
#         model = YourModel
#         fields = '__all__'
'''
        serializers_file = api_path / 'serializers.py'
        serializers_file.write_text(serializers_content, encoding='utf-8')
        result['created_files'].append(str(serializers_file))
        
        # migrations/
        migrations_path = api_path / 'migrations'
        migrations_path.mkdir(exist_ok=True)
        migrations_init = migrations_path / '__init__.py'
        migrations_init.write_text('', encoding='utf-8')
        result['created_files'].append(str(migrations_init))
    
    def _create_client_structure(self, module_path: Path, slug: str, name: str, result: dict):
        """Создает структуру клиента модуля"""
        client_path = module_path / 'client' / 'src'
        js_path = client_path / 'js'
        components_path = client_path / 'components'
        
        js_path.mkdir(parents=True, exist_ok=True)
        components_path.mkdir(parents=True, exist_ok=True)
        
        # routes.js
        routes_content = f'''/**
 * Маршруты модуля {name}
 */

export default {{
  '{slug}-home': {{
    path: '/{slug}',
    component: '@/modules/{slug}/Home.vue',
    meta: {{ title: '{name}', requiresAuth: true }}
  }},
}}
'''
        routes_file = js_path / 'routes.js'
        routes_file.write_text(routes_content, encoding='utf-8')
        result['created_files'].append(str(routes_file))
        
        # endpoints.js
        endpoints_content = f'''/**
 * API endpoints модуля {name}
 */

export default {{
  // example: '{slug}/example/',
}}
'''
        endpoints_file = js_path / 'endpoints.js'
        endpoints_file.write_text(endpoints_content, encoding='utf-8')
        result['created_files'].append(str(endpoints_file))
        
        # api.js
        api_content = f'''/**
 * API клиент модуля {name}
 */

import {{ apiClient }} from '@/js/api/manager'
import endpoints from './endpoints'

const BASE_URL = '{slug}'

export const {slug}Api = {{
  // Добавьте методы API здесь
}}
'''
        api_file = js_path / 'api.js'
        api_file.write_text(api_content, encoding='utf-8')
        result['created_files'].append(str(api_file))
        
        # Home.vue
        home_content = f'''<template>
  <div class="{slug}-home">
    <div class="container py-4">
      <h1>{{ name }}</h1>
      <p class="text-muted">{{ description }}</p>
    </div>
  </div>
</template>

<script setup>
import {{ ref }} from 'vue'

const name = ref('{name}')
const description = ref('Модуль создан через Low-Code платформу')
</script>

<style scoped>
.{slug}-home {{
  min-height: 100vh;
}}
</style>
'''
        home_file = client_path / 'Home.vue'
        home_file.write_text(home_content, encoding='utf-8')
        result['created_files'].append(str(home_file))
    
    def _create_env_file(self, module_path: Path, result: dict):
        """Создает .env файл для модуля"""
        env_file = module_path / '.env'
        env_content = '''# Переменные окружения модуля
# Добавьте специфичные для модуля переменные здесь
'''
        env_file.write_text(env_content, encoding='utf-8')
        result['created_files'].append(str(env_file))
    
    def _to_class_name(self, slug: str) -> str:
        """Преобразует slug в имя класса (PascalCase)"""
        parts = slug.split('_')
        return ''.join(word.capitalize() for word in parts)
    
    def delete_module_structure(self, slug: str) -> dict:
        """
        Удаляет структуру модуля из файловой системы.
        
        Args:
            slug: Slug модуля
            
        Returns:
            dict: Результат удаления
        """
        result = {
            'success': False,
            'errors': []
        }
        
        try:
            module_path = self.modules_dir / slug
            
            if not module_path.exists():
                result['errors'].append(f'Модуль {slug} не найден')
                return result
            
            # Удаляем директорию модуля
            import shutil
            shutil.rmtree(module_path)
            
            result['success'] = True
            logger.info(f'Структура модуля {slug} успешно удалена')
            
        except Exception as e:
            error_msg = f'Ошибка при удалении структуры модуля {slug}: {str(e)}'
            logger.error(error_msg, exc_info=True)
            result['errors'].append(error_msg)
        
        return result

