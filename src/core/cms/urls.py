from django.urls import (
    path,
    include
)
from src.core.cms.views import *

urlpatterns = [        
    # Основные CMS роуты
    path('check_access_to_page/', CheckAccesstoPage.as_view(), name='check access to page'),
    path('check_access_to_admin_panel/', CheckAccessToAdminPanel.as_view(), name='check access to admin panel'),
    path('check_access_to_component/', CheckAccessToComponents.as_view(), name='check access to component'),

    path('post_group_category/', AddGroupCategory.as_view(), name='add group category'),
    path('change_group_category/', ChangeGroupCategory.as_view(), name='change group category'),
    path('delete_group_category/<str:category_name>/', DeleteGroupCategory.as_view(), name='delete group category'),
    path('get_group_categories/', GetGroupCategories.as_view(), name="get group categories"),

    path('add_group/', AddGroup.as_view(), name='add group'),
    path('change_group/', ChangeGroup.as_view(), name='change group'),
    path('delete_group/<int:id>/', DeleteGroup.as_view(), name='delete group'),
    path('get_groups/', GetGroups.as_view(), name='get groups'),

    path('get_permissions/', GetPermissions.as_view(), name='get permissions'),
    path('add_permission/', AddPermission.as_view(), name='add permission'), 
    path('delete_permission/<int:id>/', DeletePermission.as_view(), name='delete permission'),
    path('change_permission/', ChangePermission.as_view(), name='change permission'),
    
    path('get_user_groups_and_permissions/', GetUserGroupsAndPermissions.as_view(), name='get user groups and permissions'),
    path('get_user_groups/', GetGroupsByCategory.as_view(), name='get user groups'),
    path('get_user_permissions/', GetUserPermissions.as_view(), name='get user permissions'),
    path('add_user_permission/', AddUserPermission.as_view(), name='add user permission'),
    path('remove_user_permission/', RemoveUserPermission.as_view(), name='remove user permission'),
    path('add_user_group/', AddUserGroup.as_view(), name='add user group'),
    path('remove_user_group/', RemoveUserGroup.as_view(), name='remove user group'),
    path('add_groups_permissions/', AddGroupPermission.as_view(), name='add groups permissions'),
    path('remove_groups_permissions/', RemoveGroupPermission.as_view(), name='remove groups permissions'),
    path('get_permissions_by_category/', GetPermissionsByCategory.as_view(), name='get permissions by category'),
    path('get_user_name/', GetUserName.as_view(), name='get user name'),
    path('users/<int:user_id>/public-info/', UserPublicInfoView.as_view(), name='user public info'),
    path('patch-all-project-pages', PatchAllProgectPages.as_view(), name='set all pages'),
    path('get-cms-pages', GetCMSPages.as_view(), name='get all pages'),
    path('put-cms-pages', UpdatePageLiminationType.as_view(), name='put all pages'),
    path('get-closed-pages/', GetClosedPagesForUser.as_view(), name='get closed pages'),
    path('get-closed-pages-for-user/', GetClosedPagesForUser.as_view(), name='get closed pages for user'),
    
    path('add-page-component/', AddPageComponent.as_view(), name='add page component'),
    path('remove-page-component/', RemovePageComponent.as_view(), name='remove page component'),
    path('update-page-component/', UpdatePageComponent.as_view(), name='update page component'),
    path('get-page-components/', GetPageComponents.as_view(), name='get page components')
]
