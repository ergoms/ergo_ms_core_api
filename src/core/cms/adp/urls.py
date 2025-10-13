from django.urls import (
    path
)

from rest_framework_simplejwt.views import (
    TokenRefreshView
)

from src.core.cms.adp.views import (
    UserRegistrationValidationView,
    UserRegistrationView,
    UserAuthorizationView,
    SendConfirmationCodeView,
    VerifyConfirmationCodeView,
    ProtectedView,
    ChangePasswordView,
    UserDevicesView,
    UserDeviceDetailView,
    UserProfileView,
    UserSecuritySettingsView,
)

urlpatterns = [
    path('validate-registration/', UserRegistrationValidationView.as_view(), name='validate_registration'),
    path('registration/', UserRegistrationView.as_view(), name='registration'),
    path('authorization/', UserAuthorizationView.as_view(), name='authorization'),

    path('send-code/', SendConfirmationCodeView.as_view(), name="send_code"),
    path('verify-code/', VerifyConfirmationCodeView.as_view(), name="verify_code"),

    path('token-refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('protected/', ProtectedView.as_view(), name='protected'),
    
    # Security endpoints
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('devices/', UserDevicesView.as_view(), name='user_devices'),
    path('devices/<int:device_id>/', UserDeviceDetailView.as_view(), name='user_device_detail'),
    
    # Profile endpoints
    path('profile/', UserProfileView.as_view(), name='user_profile'),
    path('security-settings/', UserSecuritySettingsView.as_view(), name='user_security_settings'),
]