"""
Каталог platform-контрактов ModuleBridge и hook discovery.

Единый источник имён групп, событий и whitelist для линтера изоляции ядра.
Модули регистрируют провайдеры в integrations.py; ядро — в соответствующих integrations.
"""

from __future__ import annotations

# --- Groups (bridge.provide_many) ---

# Единый контракт session-claims: дескриптор
# {claim, request_attr?, entity_key?, resolve?, required_guard?}.
# Модуль декларирует свои session-claims одним дескриптором; ядро выводит из них
# список JWT claims, карту entity-resolver'ов и request-атрибуты.
SESSION_CLAIMS_GROUP = 'session_context.claims'

AUDIT_ACTION_DEFINITIONS_GROUP = 'audit.action_definitions'
# Измерения аудита (scope): по чему фильтровать/группировать журнал.
# Дескриптор: {key, label, resolve(request)->value|None, filter_param?, indexed?,
# read_guard?}. read_guard=True ограничивает чтение журнала не-админам.
AUDIT_SCOPE_DIMENSIONS_GROUP = 'audit.scope_dimensions'
NOTIFICATIONS_EVENT_DEFINITIONS_GROUP = 'notifications.event_definitions'
NOTIFICATIONS_EMAIL_CONTEXT_GROUP = 'notifications.email_context'

# --- Events (bridge.subscribe_to / emit / emit_first) ---

ADP_PERMISSION_CHECK = 'adp.permission_check'
AUDIT_CAN_READ = 'audit.can_read'
AUDIT_RECORD = 'audit.record'

CORE_USER_DELETE = 'core.user_delete'
CORE_BULK_USER_CREATE = 'core.bulk_user_create'

# Провайдер возвращает dict session-claims для JWT при логине (или None).
SESSION_RESTORE_CLAIMS = 'session.restore_claims'

MENU_PREPARE_VISIBILITY = 'menu.prepare_visibility'
MENU_CAN_SEE_ITEM = 'menu.can_see_item'

# --- Core bridge op prefixes (validate_module_isolation whitelist) ---

CORE_BRIDGE_PREFIXES = ('audit.', 'notifications.', 'core.')
