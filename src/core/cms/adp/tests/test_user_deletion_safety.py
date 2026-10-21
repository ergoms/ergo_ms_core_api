from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models.deletion import ProtectedError
from django.db.utils import ProgrammingError
from django.test import TestCase

from src.core.cms.adp.models import UserProfile
from src.core.cms.adp.services import user_deletion as service


class UserDeletionSafetyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='delete-safety')
        UserProfile.objects.get_or_create(user=self.user)

    def test_blocked_deletion_rolls_back_core_cleanup_and_local_hooks(self):
        def hook(*args, **kwargs):
            get_user_model().objects.filter(pk=self.user.pk).update(first_name='changed')

        with patch.object(service, 'revoke_user_auth'), patch.object(service, 'detach_person'), patch.object(
            service.bridge, 'emit', side_effect=hook,
        ), patch.object(service, '_delete_user_record', side_effect=service.UserDeletionBlockedError('blocked')):
            with self.assertRaises(service.UserDeletionBlockedError):
                service.delete_admin_user(self.user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

    def test_listener_prevents_sql_fallback_after_orm_failure(self):
        with patch.object(self.user, 'delete', side_effect=ProgrammingError('missing table')), patch.object(
            service.pre_delete, 'has_listeners', return_value=True,
        ), patch.object(service, '_delete_existing_user_fk_rows') as cleanup, patch.object(
            service, '_delete_user_sql',
        ) as delete:
            with self.assertRaises(service.UserDeletionBlockedError):
                service._delete_user_record(self.user)
        cleanup.assert_not_called()
        delete.assert_not_called()
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_database_error_is_rolled_back_before_legacy_fallback(self):
        def fail_in_database():
            with connection.cursor() as cursor:
                cursor.execute('SELECT * FROM core_user_deletion_nonexistent_table')

        with patch.object(self.user, 'delete', side_effect=fail_in_database), patch.object(
            service.pre_delete, 'has_listeners', return_value=False,
        ), patch.object(service, '_delete_existing_user_fk_rows', return_value=0), patch.object(
            service, '_delete_user_sql',
        ) as delete:
            service._delete_user_record(self.user)
        delete.assert_called_once_with(self.user.pk)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_protected_relations_never_use_sql_fallback(self):
        with patch.object(self.user, 'delete', side_effect=ProtectedError('protected', set())), patch.object(
            service, '_delete_user_sql',
        ) as delete:
            with self.assertRaises(service.UserDeletionBlockedError):
                service._delete_user_record(self.user)
        delete.assert_not_called()
