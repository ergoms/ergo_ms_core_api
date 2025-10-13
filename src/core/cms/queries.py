def get_users_permissions(user_id: int):
     return tuple(
         [
             """
                select auth_permission.name from auth_user
                join auth_user_user_permissions on auth_user.id = auth_user_user_permissions.user_id
                join auth_permission on auth_user_user_permissions.permission_id = auth_permission.id
                where auth_user.id = %s
             """,
             tuple([user_id]),
         ]
     )

def get_users_group(user_id: int):
     return tuple(
         [
             """
                select auth_group.name from auth_user
                join auth_user_groups on auth_user.id = auth_user_groups.user_id
                join auth_group on auth_user_groups.group_id = auth_group.id
                where auth_user.id = %s
             """,
             tuple([user_id]),
         ]
     )

def get_users_group_permissions(user_id: int):
     return tuple(
         [
             """
                select auth_permission.name from auth_user
                join auth_user_groups on auth_user.id = auth_user_groups.user_id
                join auth_group_permissions on auth_user_groups.group_id = auth_group_permissions.group_id
                join auth_permission on auth_group_permissions.permission_id = auth_permission.id
                where auth_user.id = %s
             """,
             tuple([user_id]),
         ]
     )
def get_group_permissions(group_name: str):
     return tuple(
          [
            """
                select auth_permission.name from auth_group
                join auth_group_permissions on auth_group.id = auth_group_permissions.group_id
                join auth_permission on auth_group_permissions.permission_id = auth_permission.id
                where auth_group.name = %s
            """,
            tuple([group_name]),
          ]
     )