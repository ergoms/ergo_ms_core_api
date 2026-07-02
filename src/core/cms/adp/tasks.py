"""
Celery задачи для административной панели
"""
import logging
import pandas as pd
from celery import shared_task
from django.db import transaction
from django.contrib.auth.models import User

from src.core.integrations import bridge
from src.core.cms.adp.services.import_users_passwords import store_import_passwords
from src.core.cms.adp.services.import_users_welcome import (
    normalize_welcome_templates,
    render_welcome_email,
    send_import_welcome_email,
)
from src.core.cms.adp.services.registration import RegistrationService
from src.core.utils.methods import generate_secure_random_password

logger = logging.getLogger('celery.core.cms.adp')

MAX_LOGS_IN_META = 1000


def _import_meta(current, total, created, skipped, progress, accumulated_logs, last_log):
    logs = accumulated_logs[-MAX_LOGS_IN_META:].copy()
    meta = {
        'current': current,
        'total': total,
        'created': created,
        'skipped': skipped,
        'progress': progress,
        'logs': logs,
        'logs_total': len(accumulated_logs),
        'last_log': last_log,
    }
    return meta


@shared_task(bind=True, name='core.cms.adp.import_users')
def import_users_task(
    self,
    file_content,
    file_name,
    initiated_by_user_id=None,
    send_welcome_emails=False,
    welcome_email_subject='',
    welcome_email_body='',
):
    """
    Celery задача для импорта пользователей из Excel/CSV файла.

    send_welcome_emails: отправлять приветственные письма пользователям с email.
    welcome_email_subject/body: шаблоны с плейсхолдерами {username}, {full_name}, ...
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
            'logs': [],
            'emails_sent': 0,
            'emails_failed': 0,
            'emails_skipped_no_email': 0,
        }
        created_credentials = []
        welcome_subject_template, welcome_body_template = normalize_welcome_templates(
            welcome_email_subject,
            welcome_email_body,
        )
        
        logger.info(f'Файл прочитан. Всего строк: {total_rows}')
        
        # Накопленные логи для передачи клиенту
        accumulated_logs = []
        
        # Начальное обновление прогресса
        start_log = {'level': 'info', 'message': f'Начало импорта. Всего строк: {total_rows}'}
        accumulated_logs.append(start_log)
        self.update_state(
            state='PROGRESS',
            meta=_import_meta(0, total_rows, 0, 0, 0, accumulated_logs, start_log)
        )
        
        # Обрабатываем каждую строку; подавляем LMS UserProfile на время всего импорта.
        bridge.emit('core.bulk_user_create', phase='start')
        try:
            for index, row in df.iterrows():
                log_entry = None

                try:
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

                    if not last_name or not first_name or not username:
                        error_msg = f'Строка {index + 2}: пропущена - пустые обязательные поля'
                        logger.warning(error_msg)
                        results['errors'].append(error_msg)
                        log_entry = {'level': 'warn', 'message': error_msg}
                        results['logs'].append(log_entry)
                        accumulated_logs.append(log_entry)
                        results['skipped'] += 1
                        progress = int((index + 1) / total_rows * 100)
                        self.update_state(
                            state='PROGRESS',
                            meta=_import_meta(
                                index + 1, total_rows, results['created'], results['skipped'],
                                progress, accumulated_logs, log_entry,
                            ),
                        )
                        continue

                    if User.objects.filter(username__iexact=username).exists():
                        skip_msg = f'Строка {index + 2}: логин "{username}" уже занят'
                        logger.warning(skip_msg)
                        log_entry = {'level': 'warn', 'message': skip_msg}
                        results['logs'].append(log_entry)
                        accumulated_logs.append(log_entry)
                        results['skipped'] += 1
                        progress = int((index + 1) / total_rows * 100)
                        self.update_state(
                            state='PROGRESS',
                            meta=_import_meta(
                                index + 1, total_rows, results['created'], results['skipped'],
                                progress, accumulated_logs, log_entry,
                            ),
                        )
                        continue

                    email_duplicate_error = RegistrationService.validate_email_uniqueness(email)
                    if email and email_duplicate_error:
                        skip_msg = f'Строка {index + 2}: {email_duplicate_error}'
                        logger.warning(skip_msg)
                        log_entry = {'level': 'warn', 'message': skip_msg}
                        results['logs'].append(log_entry)
                        accumulated_logs.append(log_entry)
                        results['skipped'] += 1
                        progress = int((index + 1) / total_rows * 100)
                        self.update_state(
                            state='PROGRESS',
                            meta=_import_meta(
                                index + 1, total_rows, results['created'], results['skipped'],
                                progress, accumulated_logs, log_entry,
                            ),
                        )
                        continue

                    with transaction.atomic():
                        user_password = generate_secure_random_password()
                        user = User.objects.create_user(
                            username=username,
                            first_name=first_name,
                            last_name=last_name,
                            middle_name=middle_name if middle_name else '',
                            email=email if email else '',
                            password=user_password,
                        )

                        created_credentials.append({
                            'last_name': last_name,
                            'first_name': first_name,
                            'middle_name': middle_name,
                            'username': username,
                            'email': email,
                            'password': user_password,
                        })

                        if send_welcome_emails:
                            if email:
                                rendered_subject, rendered_body = render_welcome_email(
                                    user,
                                    subject_template=welcome_subject_template,
                                    body_template=welcome_body_template,
                                    password=user_password,
                                )
                                email_sent, email_error = send_import_welcome_email(
                                    email,
                                    rendered_subject,
                                    rendered_body,
                                )
                                if email_sent:
                                    results['emails_sent'] += 1
                                else:
                                    results['emails_failed'] += 1
                                    warn_msg = (
                                        f'Строка {index + 2}: пользователь создан, '
                                        f'но письмо не отправлено'
                                    )
                                    log_entry = {'level': 'warn', 'message': warn_msg}
                                    results['logs'].append(log_entry)
                                    accumulated_logs.append(log_entry)
                                    if email_error:
                                        logger.warning(
                                            'Не удалось отправить приветственное письмо для %s: %s',
                                            username,
                                            email_error,
                                        )
                            else:
                                results['emails_skipped_no_email'] += 1

                        del user_password

                    results['created'] += 1
                    if not log_entry or log_entry.get('level') != 'warn':
                        success_msg = f'Строка {index + 2}: создан "{last_name} {first_name}" ({username})'
                        logger.info('Создан пользователь ID=%s', user.id)
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

                progress = int((index + 1) / total_rows * 100)
                self.update_state(
                    state='PROGRESS',
                    meta=_import_meta(
                        index + 1,
                        total_rows,
                        results['created'],
                        results['skipped'],
                        progress,
                        accumulated_logs,
                        log_entry,
                    ),
                )
        finally:
            bridge.emit('core.bulk_user_create', phase='end')
        
        # Финальные результаты
        logger.info(f'Импорт завершен. Создано: {results["created"]}, пропущено: {results["skipped"]}')
        
        # Финальное обновление прогресса до 100%
        final_log = {'level': 'success', 'message': f'Импорт завершён! Создано: {results["created"]}, пропущено: {results["skipped"]}'}
        accumulated_logs.append(final_log)
        self.update_state(
            state='PROGRESS',
            meta=_import_meta(total_rows, total_rows, results['created'], results['skipped'], 100, accumulated_logs, final_log)
        )

        passwords_available = bool(created_credentials)
        if passwords_available and initiated_by_user_id:
            store_import_passwords(self.request.id, initiated_by_user_id, created_credentials)

        return {
            'success': True,
            'created': results['created'],
            'skipped': results['skipped'],
            'total': total_rows,
            'errors': results['errors'],
            'logs': results['logs'],
            'passwords_available': passwords_available,
            'emails_sent': results['emails_sent'],
            'emails_failed': results['emails_failed'],
            'emails_skipped_no_email': results['emails_skipped_no_email'],
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
