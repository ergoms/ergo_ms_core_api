from django.urls import path

from src.core.cms.views import (
    CheckAccessToAdminPanel,
    GetUserName,
    UserPublicInfoView,
    SyncAllProjectPages,
    GetCMSPages,
)
from src.core.cms.disabled_modules_view import DisabledModulesView

urlpatterns = [
    path('disabled-modules/', DisabledModulesView.as_view(), name='disabled-modules'),

    path('check_access_to_admin_panel/', CheckAccessToAdminPanel.as_view(), name='check access to admin panel'),

    path('get_user_name/', GetUserName.as_view(), name='get user name'),
    path('users/by-ref/<uuid:ref>/public-info/', UserPublicInfoView.as_view(), name='user public info by ref'),

    path('patch-all-project-pages', SyncAllProjectPages.as_view(), name='set all pages'),
    path('get-cms-pages', GetCMSPages.as_view(), name='get all pages'),
]
