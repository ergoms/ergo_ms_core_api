from django.contrib.auth.models import User

from src.core.cms.models import ExpandedPermission


def GetUserExpandedPermissions(user: User):
    result = []
    seen_ids = set()

    def append_expanded(permission):
        if permission.id in seen_ids:
            return
        try:
            exp = ExpandedPermission.objects.get(permission=permission)
        except ExpandedPermission.DoesNotExist:
            return
        seen_ids.add(permission.id)
        result.append(exp)

    for group in user.groups.all():
        for permission in group.permissions.all():
            append_expanded(permission)

    for perm in user.user_permissions.all():
        append_expanded(perm)

    return result
