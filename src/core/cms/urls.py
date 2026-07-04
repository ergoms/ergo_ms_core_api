from django.urls import path

from src.core.cms.views import (
    CheckAccessToAdminPanel,
    GetUserName,
    UserPublicInfoView,
    PatchAllProgectPages,
    GetCMSPages,
    UpdatePageLiminationType,
    AddPageComponent,
    RemovePageComponent,
    UpdatePageComponent,
    GetPageComponents,
)
from src.core.cms.disabled_modules_view import DisabledModulesView

urlpatterns = [
    path('disabled-modules/', DisabledModulesView.as_view(), name='disabled-modules'),

    path('check_access_to_admin_panel/', CheckAccessToAdminPanel.as_view(), name='check access to admin panel'),

    path('get_user_name/', GetUserName.as_view(), name='get user name'),
    path('users/by-ref/<uuid:ref>/public-info/', UserPublicInfoView.as_view(), name='user public info by ref'),

    path('patch-all-project-pages', PatchAllProgectPages.as_view(), name='set all pages'),
    path('get-cms-pages', GetCMSPages.as_view(), name='get all pages'),
    path('put-cms-pages', UpdatePageLiminationType.as_view(), name='put all pages'),

    path('add-page-component/', AddPageComponent.as_view(), name='add page component'),
    path('remove-page-component/', RemovePageComponent.as_view(), name='remove page component'),
    path('update-page-component/', UpdatePageComponent.as_view(), name='update page component'),
    path('get-page-components/', GetPageComponents.as_view(), name='get page components'),
]
