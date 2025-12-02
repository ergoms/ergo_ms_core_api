from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import pre_delete
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)


class LcpModule(models.Model):
    """Модуль созданный через Low-Code платформу"""
    
    name = models.CharField(
        max_length=100,
        verbose_name='Название модуля'
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name='Slug'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Описание'
    )
    icon = models.CharField(
        max_length=50,
        default='Box',
        verbose_name='Иконка (Lucide)'
    )
    color = models.CharField(
        max_length=20,
        default='primary',
        verbose_name='Цвет темы'
    )
    
    # Настройки модуля
    settings = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Настройки'
    )
    
    # Глобальные переменные модуля
    global_variables = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Глобальные переменные'
    )
    
    # Порядок в меню
    menu_order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок в меню'
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активен'
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lcp_modules',
        verbose_name='Создатель'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    class Meta:
        ordering = ['menu_order', 'name']
        verbose_name = 'LCP Модуль'
        verbose_name_plural = 'LCP Модули'
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        """Переопределяем save для создания структуры модуля"""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Создаем структуру только для новых модулей
        if is_new:
            try:
                from src.core.lcp.services.module_structure import ModuleStructureService
                service = ModuleStructureService()
                result = service.create_module_structure(
                    slug=self.slug,
                    name=self.name,
                    description=self.description
                )
                
                if not result['success']:
                    logger.warning(
                        f'Не удалось создать структуру модуля {self.slug}: '
                        f'{", ".join(result["errors"])}'
                    )
                else:
                    logger.info(
                        f'Структура модуля {self.slug} создана: '
                        f'{len(result["created_files"])} файлов'
                    )
            except Exception as e:
                logger.error(
                    f'Ошибка при создании структуры модуля {self.slug}: {str(e)}',
                    exc_info=True
                )


@receiver(pre_delete, sender=LcpModule)
def delete_module_structure(sender, instance, **kwargs):
    """Удаляет структуру модуля при удалении из БД"""
    try:
        from src.core.lcp.services.module_structure import ModuleStructureService
        service = ModuleStructureService()
        result = service.delete_module_structure(instance.slug)
        
        if not result['success']:
            logger.warning(
                f'Не удалось удалить структуру модуля {instance.slug}: '
                f'{", ".join(result["errors"])}'
            )
    except Exception as e:
        logger.error(
            f'Ошибка при удалении структуры модуля {instance.slug}: {str(e)}',
            exc_info=True
        )
    
    def save(self, *args, **kwargs):
        """Переопределяем save для создания структуры модуля"""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Создаем структуру только для новых модулей
        if is_new:
            try:
                from src.core.lcp.services.module_structure import ModuleStructureService
                service = ModuleStructureService()
                result = service.create_module_structure(
                    slug=self.slug,
                    name=self.name,
                    description=self.description
                )
                
                if not result['success']:
                    logger.warning(
                        f'Не удалось создать структуру модуля {self.slug}: '
                        f'{", ".join(result["errors"])}'
                    )
                else:
                    logger.info(
                        f'Структура модуля {self.slug} создана: '
                        f'{len(result["created_files"])} файлов'
                    )
            except Exception as e:
                logger.error(
                    f'Ошибка при создании структуры модуля {self.slug}: {str(e)}',
                    exc_info=True
                )


@receiver(pre_delete, sender=LcpModule)
def delete_module_structure(sender, instance, **kwargs):
    """Удаляет структуру модуля при удалении из БД"""
    try:
        from src.core.lcp.services.module_structure import ModuleStructureService
        service = ModuleStructureService()
        result = service.delete_module_structure(instance.slug)
        
        if not result['success']:
            logger.warning(
                f'Не удалось удалить структуру модуля {instance.slug}: '
                f'{", ".join(result["errors"])}'
            )
    except Exception as e:
        logger.error(
            f'Ошибка при удалении структуры модуля {instance.slug}: {str(e)}',
            exc_info=True
        )


