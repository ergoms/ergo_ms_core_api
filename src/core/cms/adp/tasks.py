"""
Celery задачи для административной панели
"""
import logging
import pandas as pd
from celery import shared_task
from django.db import transaction
from django.db.models.signals import post_save
from django.contrib.auth.models import User

logger = logging.getLogger('celery.core.cms.adp')


@shared_task(bind=True, name='core.cms.adp.import_users')
def import_users_task(self, file_content, file_name, skip_welcome_emails=False):
    """
    Celery задача для импорта пользователей из Excel/CSV файла
    
    Args:
        self: Task instance (bind=True)
        file_content: Содержимое файла в байтах
        file_name: Имя файла для определения типа
        skip_welcome_emails: Не отправлять приветственные письма
    
    Returns:
        dict: Результаты импорта
    """
    logger.info(f'Начало импорта пользователей из файла: {file_name}')
    
    try:
        # Читаем файл
        from io import BytesIO
        file_io = BytesIO(file_content)
        
        if file_name.lower().endswith('.csv'):
            # Пробуем разные кодировки для CSV
            try:
                df = pd.read_csv(file_io, encoding='utf-8')
            except UnicodeDecodeError:
                file_io.seek(0)
                df = pd.read_csv(file_io, encoding='cp1251')
        else:
            df = pd.read_excel(file_io, header=0)
        
        # Нормализуем названия колонок
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # Маппинг возможных названий колонок
        column_mapping = {
            'фамилия': ['фамилия', 'last_name', 'lastname', 'surname'],
            'имя': ['имя', 'first_name', 'firstname', 'name'],
            'отчество': ['отчество', 'middle_name', 'middlename', 'patronymic'],
            'логин': ['логин', 'login', 'username', 'user'],
            'email': ['email', 'e-mail', 'почта', 'электронная почта', 'mail']
        }
        
        # Находим реальные названия колонок
        found_columns = {}
        for target, variants in column_mapping.items():
            for col in df.columns:
                if col in variants:
                    found_columns[target] = col
                    break
        
        # Проверяем наличие обязательных колонок
        required = ['фамилия', 'имя', 'логин']
        missing = [col for col in required if col not in found_columns]
        if missing:
            error_msg = f'Отсутствуют обязательные колонки: {", ".join(missing)}'
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'created': 0,
                'skipped': 0,
                'total': 0
            }
        
        total_rows = len(df)
        results = {
            'created': 0,
            'skipped': 0,
            'errors': [],
            'logs': []
        }
        
        logger.info(f'Файл прочитан. Всего строк: {total_rows}')
        
        # Накопленные логи для передачи клиенту
        accumulated_logs = []
        
        # Начальное обновление прогресса
        start_log = {'level': 'info', 'message': f'Начало импорта. Всего строк: {total_rows}'}
        accumulated_logs.append(start_log)
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': total_rows,
                'created': 0,
                'skipped': 0,
                'progress': 0,
                'logs': accumulated_logs.copy(),
                'last_log': start_log
            }
        )
        
        # Обрабатываем каждую строку
        for index, row in df.iterrows():
            log_entry = None
            
            try:
                # Извлекаем данные
                last_name = str(row.get(found_columns['фамилия'], '')).strip()
                first_name = str(row.get(found_columns['имя'], '')).strip()
                middle_name = ''
                if 'отчество' in found_columns:
                    middle_name = str(row.get(found_columns['отчество'], '')).strip()
                    if pd.isna(row.get(found_columns['отчество'])):
                        middle_name = ''
                
                username = str(row.get(found_columns['логин'], '')).strip()
                email = ''
                if 'email' in found_columns:
                    email = str(row.get(found_columns['email'], '')).strip()
                    if pd.isna(row.get(found_columns['email'])):
                        email = ''
                
                # Очищаем от NaN
                if pd.isna(last_name) or last_name == 'nan':
                    last_name = ''
                if pd.isna(first_name) or first_name == 'nan':
                    first_name = ''
                if pd.isna(middle_name) or middle_name == 'nan':
                    middle_name = ''
                if pd.isna(username) or username == 'nan':
                    username = ''
                if pd.isna(email) or email == 'nan':
                    email = ''
                
                # Проверяем обязательные поля
                if not last_name or not first_name or not username:
                    error_msg = f'Строка {index + 2}: пропущена - пустые обязательные поля'
                    logger.warning(error_msg)
                    results['errors'].append(error_msg)
                    log_entry = {'level': 'warn', 'message': error_msg}
                    results['logs'].append(log_entry)
                    accumulated_logs.append(log_entry)
                    results['skipped'] += 1
                    # Обновляем прогресс перед continue
                    progress = int((index + 1) / total_rows * 100)
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'current': index + 1,
                            'total': total_rows,
                            'created': results['created'],
                            'skipped': results['skipped'],
                            'progress': progress,
                            'logs': accumulated_logs.copy(),
                            'last_log': log_entry
                        }
                    )
                    continue
                
                # Проверяем дубликат по ФИО
                if User.objects.filter(
                    last_name__iexact=last_name,
                    first_name__iexact=first_name,
                    middle_name__iexact=middle_name if middle_name else ''
                ).exists():
                    skip_msg = f'Строка {index + 2}: пользователь "{last_name} {first_name}" уже существует'
                    logger.warning(skip_msg)
                    log_entry = {'level': 'warn', 'message': skip_msg}
                    results['logs'].append(log_entry)
                    accumulated_logs.append(log_entry)
                    results['skipped'] += 1
                    # Обновляем прогресс перед continue
                    progress = int((index + 1) / total_rows * 100)
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'current': index + 1,
                            'total': total_rows,
                            'created': results['created'],
                            'skipped': results['skipped'],
                            'progress': progress,
                            'logs': accumulated_logs.copy(),
                            'last_log': log_entry
                        }
                    )
                    continue
                
                # Проверяем дубликат логина
                if User.objects.filter(username__iexact=username).exists():
                    skip_msg = f'Строка {index + 2}: логин "{username}" уже занят'
                    logger.warning(skip_msg)
                    log_entry = {'level': 'warn', 'message': skip_msg}
                    results['logs'].append(log_entry)
                    accumulated_logs.append(log_entry)
                    results['skipped'] += 1
                    # Обновляем прогресс перед continue
                    progress = int((index + 1) / total_rows * 100)
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'current': index + 1,
                            'total': total_rows,
                            'created': results['created'],
                            'skipped': results['skipped'],
                            'progress': progress,
                            'logs': accumulated_logs.copy(),
                            'last_log': log_entry
                        }
                    )
                    continue
                
                # Проверяем дубликат email
                if email and User.objects.filter(email__iexact=email).exists():
                    skip_msg = f'Строка {index + 2}: email "{email}" уже используется'
                    logger.warning(skip_msg)
                    log_entry = {'level': 'warn', 'message': skip_msg}
                    results['logs'].append(log_entry)
                    accumulated_logs.append(log_entry)
                    results['skipped'] += 1
                    # Обновляем прогресс перед continue
                    progress = int((index + 1) / total_rows * 100)
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'current': index + 1,
                            'total': total_rows,
                            'created': results['created'],
                            'skipped': results['skipped'],
                            'progress': progress,
                            'logs': accumulated_logs.copy(),
                            'last_log': log_entry
                        }
                    )
                    continue
                
                # Создаём пользователя
                with transaction.atomic():
                    # Временно отключаем сигнал для пропуска приветственных писем
                    if skip_welcome_emails:
                        try:
                            from modules.lms.api.signals import create_user_profile
                            post_save.disconnect(create_user_profile, sender=User)
                        except ImportError:
                            pass
                    
                    try:
                        user = User.objects.create_user(
                            username=username,
                            first_name=first_name,
                            last_name=last_name,
                            middle_name=middle_name if middle_name else '',
                            email=email if email else '',
                            password='1'
                        )
                    finally:
                        if skip_welcome_emails:
                            try:
                                from modules.lms.api.signals import create_user_profile
                                post_save.connect(create_user_profile, sender=User)
                            except ImportError:
                                pass
                
                results['created'] += 1
                success_msg = f'Строка {index + 2}: создан "{last_name} {first_name}" ({username})'
                logger.info(f'Создан пользователь ID={user.id}')
                log_entry = {'level': 'success', 'message': success_msg}
                results['logs'].append(log_entry)
                accumulated_logs.append(log_entry)
                
            except Exception as e:
                error_msg = f'Строка {index + 2}: ошибка - {str(e)}'
                logger.error(error_msg, exc_info=True)
                results['errors'].append(error_msg)
                log_entry = {'level': 'error', 'message': error_msg}
                results['logs'].append(log_entry)
                accumulated_logs.append(log_entry)
            
            # Обновляем прогресс задачи с последним логом
            progress = int((index + 1) / total_rows * 100)
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': index + 1,
                    'total': total_rows,
                    'created': results['created'],
                    'skipped': results['skipped'],
                    'progress': progress,
                    'logs': accumulated_logs.copy(),
                    'last_log': log_entry
                }
            )
        
        # Финальные результаты
        logger.info(f'Импорт завершен. Создано: {results["created"]}, пропущено: {results["skipped"]}')
        
        # Финальное обновление прогресса до 100%
        final_log = {'level': 'success', 'message': f'Импорт завершён! Создано: {results["created"]}, пропущено: {results["skipped"]}'}
        accumulated_logs.append(final_log)
        self.update_state(
            state='PROGRESS',
            meta={
                'current': total_rows,
                'total': total_rows,
                'created': results['created'],
                'skipped': results['skipped'],
                'progress': 100,
                'logs': accumulated_logs.copy(),
                'last_log': final_log
            }
        )
        
        return {
            'success': True,
            'created': results['created'],
            'skipped': results['skipped'],
            'total': total_rows,
            'errors': results['errors'],
            'logs': results['logs']
        }
        
    except Exception as e:
        error_msg = f'Критическая ошибка при импорте: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {
            'success': False,
            'error': error_msg,
            'created': 0,
            'skipped': 0,
            'total': 0,
            'errors': [error_msg],
            'logs': [{'level': 'error', 'message': error_msg}]
        }
