"""Сигналы для инкрементальной индексации."""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from src.core.audit.models import AuditEvent
from src.core.client_monitor.models import ClientMonitorSession
from src.core.cms.adp.models import (
  ModulePermission,
  RegistrationInvitation,
  Role,
  RoleGroup,
  UserProfileChangeRequest,
)
from src.core.search.core_indexes import (
  INDEX_AUDIT,
  INDEX_CLIENT_MONITOR,
  INDEX_INVITATIONS,
  INDEX_MODULE_PERMISSIONS,
  INDEX_PROFILE_CHANGE,
  INDEX_ROLE_GROUPS,
  INDEX_ROLES,
  INDEX_USERS,
)
from src.core.search.registry import get_index
from src.core.search.sync import ensure_registry_loaded
from src.core.search.tasks import delete_document_task, index_document_task

from django.contrib.auth import get_user_model

User = get_user_model()

_MODEL_INDEX = {
  User: (INDEX_USERS, '_build_user_document', 'core_indexes'),
  AuditEvent: (INDEX_AUDIT, '_build_audit_document', 'core_indexes'),
  RegistrationInvitation: (INDEX_INVITATIONS, '_build_invitation_document', 'core_indexes'),
  UserProfileChangeRequest: (INDEX_PROFILE_CHANGE, '_build_profile_change_document', 'core_indexes'),
  ClientMonitorSession: (INDEX_CLIENT_MONITOR, '_build_client_monitor_document', 'core_indexes'),
  Role: (INDEX_ROLES, '_build_role_document', 'core_indexes'),
  RoleGroup: (INDEX_ROLE_GROUPS, '_build_role_group_document', 'core_indexes'),
  ModulePermission: (INDEX_MODULE_PERMISSIONS, '_build_module_permission_document', 'core_indexes'),
}


def _schedule_index(index_uid: str, instance) -> None:
  ensure_registry_loaded()
  defn = get_index(index_uid)
  if not defn or not defn.build_document:
    return
  document = defn.build_document(instance)
  index_document_task.delay(index_uid, document)


def _schedule_delete(index_uid: str, pk) -> None:
  delete_document_task.delay(index_uid, str(pk))


def _connect_model(model, index_uid: str):
  @receiver(post_save, sender=model)
  def _on_save(sender, instance, **kwargs):
    _schedule_index(index_uid, instance)

  @receiver(post_delete, sender=model)
  def _on_delete(sender, instance, **kwargs):
    _schedule_delete(index_uid, instance.pk)


for _model, (_uid, _builder, _mod) in _MODEL_INDEX.items():
  _connect_model(_model, _uid)
