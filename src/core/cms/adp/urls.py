from django.urls import path, include

from src.core.cms.adp.token_refresh import DeviceBoundTokenRefreshView

from src.core.cms.adp.views import (
    UserRegistrationValidationView,
    UserRegistrationView,
    UserAuthorizationView,
    PasswordResetSettingsView,
    SendConfirmationCodeView,
    VerifyConfirmationCodeView,
    ResetPasswordView,
    ProtectedView,
    ChangePasswordView,
    UserDevicesView,
    UserDeviceDetailView,
    UserProfileView,
    UserMenuView,
    UserSecuritySettingsView,
    ImportUsersView,
    ImportUsersTaskStatusView,
)

from src.core.cms.adp.views_roles import (
    RoleListView,
    RoleDetailView,
    RoleGroupListView,
    RoleGroupDetailView,
    PolicyListView,
    PolicyDetailView,
    UserRoleAssignView,
    UserPermissionsView,
    CheckURLAccessView,
    ModulePermissionListView,
    ModulePermissionDetailView,
    AdminUserRoleListView,
    AdminUserDetailView,
    AdminUserAvatarView,
    AdminUserResetPasswordView,
)

from src.core.cms.adp.views_presence import UserPresenceBatchView
from src.core.cms.adp.views_invitations import (
    RegistrationSettingsView,
    ValidateInvitationView,
    RegistrationInvitationListView,
    RegistrationInvitationDetailView,
    RegistrationInvitationResendView,
    RegistrationInvitationBulkCreateView,
    RegistrationInvitationBulkSendView,
    RegistrationInvitationClearView,
)

urlpatterns = [
    # Authentication endpoints
    path('registration-settings/', RegistrationSettingsView.as_view(), name='registration_settings'),
    path('password-reset-settings/', PasswordResetSettingsView.as_view(), name='password_reset_settings'),
    path('invitations/validate/', ValidateInvitationView.as_view(), name='validate_invitation'),
    path('invitations/', RegistrationInvitationListView.as_view(), name='registration_invitations'),
    path('invitations/bulk/', RegistrationInvitationBulkCreateView.as_view(), name='registration_invitations_bulk'),
    path('invitations/bulk/send/', RegistrationInvitationBulkSendView.as_view(), name='registration_invitations_bulk_send'),
    path('invitations/clear/', RegistrationInvitationClearView.as_view(), name='registration_invitations_clear'),
    path('invitations/<int:invitation_id>/', RegistrationInvitationDetailView.as_view(), name='registration_invitation_detail'),
    path(
        'invitations/<int:invitation_id>/resend/',
        RegistrationInvitationResendView.as_view(),
        name='registration_invitation_resend',
    ),
    path('validate-registration/', UserRegistrationValidationView.as_view(), name='validate_registration'),
    path('registration/', UserRegistrationView.as_view(), name='registration'),
    path('authorization/', UserAuthorizationView.as_view(), name='authorization'),

    path('send-code/', SendConfirmationCodeView.as_view(), name="send_code"),
    path('verify-code/', VerifyConfirmationCodeView.as_view(), name="verify_code"),
    path('reset-password/', ResetPasswordView.as_view(), name="reset_password"),

    path('token-refresh/', DeviceBoundTokenRefreshView.as_view(), name='token_refresh'),
    path('protected/', ProtectedView.as_view(), name='protected'),
    
    # Security endpoints
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('devices/', UserDevicesView.as_view(), name='user_devices'),
    path('devices/<int:device_id>/', UserDeviceDetailView.as_view(), name='user_device_detail'),
    
    # Profile endpoints
    path('profile/', UserProfileView.as_view(), name='user_profile'),
    path('user-menu-data/', UserMenuView.as_view(), name='user_menu_data'),
    path('security-settings/', UserSecuritySettingsView.as_view(), name='user_security_settings'),
    
    # Role and Policy Management endpoints
    path('roles/', RoleListView.as_view(), name='role_list'),
    path('roles/<int:role_id>/', RoleDetailView.as_view(), name='role_detail'),
    path('role-groups/', RoleGroupListView.as_view(), name='role_group_list'),
    path('role-groups/<int:group_id>/', RoleGroupDetailView.as_view(), name='role_group_detail'),
    path('policies/', PolicyListView.as_view(), name='policy_list'),
    path('policies/<int:policy_id>/', PolicyDetailView.as_view(), name='policy_detail'),
    path('assign-role/', UserRoleAssignView.as_view(), name='assign_role'),
    path('my-permissions/', UserPermissionsView.as_view(), name='user_permissions'),
    path('check-url-access/', CheckURLAccessView.as_view(), name='check_url_access'),
    path('module-permissions/', ModulePermissionListView.as_view(), name='module_permissions'),
    path('module-permissions/<int:permission_id>/', ModulePermissionDetailView.as_view(), name='module_permission_detail'),
    path('admin-users/', AdminUserRoleListView.as_view(), name='admin_users'),
    path('admin-users/<int:user_id>/', AdminUserDetailView.as_view(), name='admin_user_detail'),
    path('admin-users/<int:user_id>/avatar/', AdminUserAvatarView.as_view(), name='admin_user_avatar'),
    path('admin-users/<int:user_id>/reset-password/',
        AdminUserResetPasswordView.as_view(),
        name='admin_user_reset_password',
    ),
    path('presence/', UserPresenceBatchView.as_view(), name='user_presence_batch'),
    path('import-users/', ImportUsersView.as_view(), name='import_users'),
    path('import-users/status/<str:task_id>/', ImportUsersTaskStatusView.as_view(), name='import_users_status'),
    
    # Menu Management endpoints (подключаем подмодуль menu)
    path('menu/', include('src.core.cms.adp.menu.urls')),
]