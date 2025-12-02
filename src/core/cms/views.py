import re
import os

from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import (Group, Permission, User)

from src.core.utils.base.base_views import BaseAPIViewAuthMixin
from src.core.cms.models import (
    ExpandedPermission,
    Accession,
    GroupCategory,
    ExpandedGroup,
    PermissionMark,
    Accession,
    CMSPage,
    CMSPageComponent,
)
from src.core.cms.commands import GetUserExpandedPermissions
from src.core.utils.auto_api.auto_config import ModuleDiscoverer


def _normalize_path(path: str) -> str:
    """
    Приводит путь к каноничному виду:
    - оставляет '/' как есть
    - для остальных строк удаляет завершающий слеш
    """
    if not path:
        return path
    if path == '/':
        return '/'
    return path[:-1] if path.endswith('/') else path


def _discover_client_routes_index() -> dict[str, str]:
    """
    Строит индекс client-путей -> имени модуля для всех маршрутов
    из core и внешних модулей.

    Используется CMS для синхронизации и отображения страниц
    (экран ModulePagePermissions).
    """
    path_to_module: dict[str, str] = {}

    discoverer = ModuleDiscoverer()
    route_modules = discoverer.discover_client_route_modules()

    for module_key, routes_path in route_modules.items():
        # module_key имеет вид 'module:<name>' или 'core:<name>'
        try:
            _, module_name = module_key.split(':', 1)
        except ValueError:
            module_name = module_key

        try:
            with open(routes_path, 'r', encoding='utf-8') as routes_file:
                routes_content = routes_file.read()

            module_paths = re.findall(
                r'["\']path["\']\s*:\s*["\'](.*?)["\']',
                routes_content,
            )

            for route_path in module_paths:
                # приводим escape-последовательности к runtime-формату
                cleaned_path = route_path.replace('\\\\', '\\')
                normalized = _normalize_path(cleaned_path)
                # если путь уже есть, не перезаписываем — первый модуль считается основным
                path_to_module.setdefault(normalized, module_name)
        except Exception:
            # Ошибку отдельного модуля не считаем критичной для всей выборки
            continue

    return path_to_module


#Управление категорями групп
class AddGroupCategory(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Добавление категории группы",
        responses={
            200: "Категория добавлена",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
            400: "Неверный данные"
        },
         request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'category_name': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Имя категории'
                ),
                'create_admin_group': openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    description='Создать группу администраторов'
                )
            }
        )
    )
    def post(self, request: Request):
        if(request.user.is_superuser):
            cats = GroupCategory.objects.all()
            for cat in cats:
                if cat.name == request.data['category_name']:
                    return Response(
                        status=status.HTTP_400_BAD_REQUEST
                    )
            catg = GroupCategory.objects.create(name = request.data['category_name'])
            ct = ContentType.objects.get_or_create(app_label='cms', model='none')
            pm = PermissionMark.objects.get(id = 4)
            p = Permission.objects.create(codename ='Admin of Category '+ request.data['category_name'], name = request.data['category_name'] + ' redact', content_type = ct[0])
            exp =ExpandedPermission.objects.create(permission = p, group_category = catg, permission_mark = pm)
            Accession.objects.create(path = None, component_id = None, permission = exp)
            
            if request.data['create_admin_group']:
                g =Group.objects.create(name = request.data['category_name'] + ' admin')
                g.permissions.add(p)
                ExpandedGroup.objects.create(group = g, category = catg, level = 10)
            return Response(
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                status= status.HTTP_403_FORBIDDEN
            )
        
class GetGroupCategories(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="получение категорий групп",
        responses={
            200: "Категории получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
    )
    def get(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(request.user.is_superuser | access):
            cats = []
            if( request.user.is_superuser):
                categories = GroupCategory.objects.all()
                for cat in categories:
                    cats.append({"id": cat.id, "name": cat.name})
            else:
                for exp in exps:
                    if(exp.permission_mark.id==4):
                        cats.append({"id": exp.group_category.id, "name": exp.group_category.name})
            result = {"categories": cats}
            return Response(
                    result,
                    status=status.HTTP_200_OK
                )
        else:
            return Response(
                status= status.HTTP_403_FORBIDDEN
            )  

class ChangeGroupCategory(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Изменение категории группы",
        responses={
            200: "Категория изменена",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
         request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'category_name': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Имя категории'
                ),
                'new_category_name': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Новое имя категории'
                )
            }
        )
    )
    def put(self, request: Request):
        if(request.user.is_superuser):
            catg = GroupCategory.objects.get(name = request.data['category_name'])
            pm = PermissionMark.objects.get(id = 4)
            exp =ExpandedPermission.objects.get(group_category = catg, permission_mark = pm)
            p = exp.permission
            p.codename ='Admin of Category '+ request.data['new_category_name']
            p.name = request.data['new_category_name'] + ' redact'
            for egroup in ExpandedGroup.objects.filter(category= catg):
                group = egroup.group
                if(group.name == request.data['category_name'] + ' admin'):
                    group.name = request.data['new_category_name'] + ' admin'
                    group.save()
                    break
            catg.name = request.data['new_category_name']
            p.save()
            catg.save()
            return Response(
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )

class DeleteGroupCategory(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Удаление категории группы",
        responses={
            200: "Категория удалена",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
    )
    def delete(self, request: Request, category_name):
        if(request.user.is_superuser):
            catg = GroupCategory.objects.get(name = category_name)
            eg = ExpandedGroup.objects.filter(category = catg)
            for e in eg:
                g = e.group
                g.delete()
                e.delete()
            exps = ExpandedPermission.objects.filter(group_category = catg)
            for exp in exps:
                accession = Accession.objects.get(permission = exp)
                accession.delete()
                permission = exp.permission
                permission.delete()
                exp.delete()
            catg.delete()
            return Response(status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)

#Управление группами
class AddGroup(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Добавление группы",
        responses={
            200: "Группа добавлена",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
         request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'group_name': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Имя группы'
                ),
                'level': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='Уровень группы'
                ),
                'category_name': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Название категории группы'
                )
            }
        )
    )
    def post(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4 and (exp.group_category.name == request.data['category_name']):
                access = True
                break
        if(request.user.is_superuser | access):
            catg = GroupCategory.objects.get(name = request.data['category_name'])
            g = Group.objects.create(name= request.data['group_name'])
            ExpandedGroup.objects.create(group=g, category = catg, level = request.data['level'])
            return Response(
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )

class ChangeGroup(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="обновление группы",
        responses={
            200: "Группа обновлена",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
         request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'group_name': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Имя группы'
                ),
                'new_group_name': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Новое имя группы'
                ),
                'category_name': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Название категории группы'
                ),
                'level': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='Уровень группы'
                )
            }
        )
    )
    def put(self, request: Request):
        g = Group.objects.get(name = request.data['group_name'])
        eg = ExpandedGroup.objects.get(group = g)
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4 and (exp.group_category.name == eg.category.name):
                access = True
                break
        if(request.user.is_superuser | access):
            nameg = request.data['group_name']
            group = Group.objects.get(name = nameg )
            if (request.data['new_group_name'] != '') & (request.data['new_group_name'] != group.name):
                group.name = request.data['new_group_name']
            eg = ExpandedGroup.objects.get(group = group)
            if (request.data['category_name'] != '') & (request.data['category_name'] != eg.category.name):
                eg.category = GroupCategory.objects.get(name = request.data['category_name'])
            if (request.data['level'] != '') & (request.data['level'] != eg.level):
                eg.level = request.data['level']
            eg.save()
            group.save()
            return Response(
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )

class DeleteGroup(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="удаление группы",
        responses={
            200: "Группа удалена",
            401: "Не удалось удалить группу"
        },
    )
    def delete(self, request: Request, id):
        g = Group.objects.get(id=id)
        eg = ExpandedGroup.objects.get(group = g)
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4 and (exp.group_category.name == eg.category.name):
                access = True
                break
        if(request.user.is_superuser | access):
            eg.delete()
            g.delete()
            return Response(
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )

class GetGroupsByCategory(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение групп пользователя.",
        responses={
            200: "группы пользователя получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        }
    )
    def get(self, request: Request):
            user = request.user
            groups = user.groups.all()
            groups_names =[]
            for group in groups:
                groups_names.append(group.name)
            result = {"groups":groups_names}
            return Response(
                result,
                status=status.HTTP_200_OK
            )

class GetGroups(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение групп.",
        responses = {
            200: "группы получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        }
    )
    def get(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(request.user.is_superuser | access):
            groups = Group.objects.all()
            groups_list =[]
            if(request.user.is_superuser):
               for group in groups:
                    expanded_group = ExpandedGroup.objects.get(group_id = group.id)
                    permissions = group.permissions.all()
                    permissions_list = []
                    for permission in permissions:
                        permissions_list.append(permission.name)
                    tmpres = {'id':group.id, 'name':group.name, 'category':expanded_group.category.name, 'level':expanded_group.level, 'permissions':permissions_list}
                    groups_list.append(tmpres)
            else:
                cat_list=[]
                for exp in exps:
                    if exp.permission_mark.id == 4:
                        cat_list.append(exp.group_category.name)
                for cat in cat_list:                
                    for group in groups:
                        expanded_group = ExpandedGroup.objects.get(group_id = group.id)
                        if expanded_group.category.name == cat:
                            permissions = group.permissions.all()
                            permissions_list = []
                            for permission in permissions:
                                permissions_list.append(permission.name)
                            tmpres = {'id':group.id, 'name':group.name, 'category':expanded_group.category.name, 'level':expanded_group.level, 'permissions':permissions_list}
                            groups_list.append(tmpres)
            result = {"groups":groups_list}
            return Response(
                result,
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )
        
class AddGroupPermission(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Добавление прав группе",
        responses={
            200: "Права группе добавлены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'group_name': openapi.Schema(type=openapi.TYPE_STRING, description='Имя группы'),
                'permissions_name': openapi.Schema(type=openapi.TYPE_ARRAY,items=openapi.Items(type=openapi.TYPE_STRING), description='Имя права'),
                'change_other_groups': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='изменять другие группы'),
            }
        )
    )
    def post(self, request: Request):
        access = False
        group = Group.objects.get(name = request.data['group_name'])
        exp_group = ExpandedGroup.objects.get(group=group)
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4 and exp.group_category==exp_group.category:
                access = True
                break
        if(access or request.user.is_superuser):
            for permission_name in request.data['permissions_name']:
                permission = Permission.objects.get(name = permission_name)
                exp_permission = ExpandedPermission.objects.get(permission=permission)
                if(exp_permission.group_category == exp_group.category):
                    group.permissions.add(permission)
                    if(request.data['change_other_groups']):
                        groups = Group.objects.all()
                        for group in groups:
                            expand_group = ExpandedGroup.objects.get(group=group)
                            if(expand_group.level > exp_group.level and exp_group.category == expand_group.category and not(group.permissions.contains(permission))):
                                group.permissions.add(permission)
                else:
                    return Response(status=status.HTTP_400_BAD_REQUEST)
            group.save()
            return Response(status=status.HTTP_200_OK) 
        
class RemoveGroupPermission(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Удаление прав группе",
        responses={
            200: "Права группе удалены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'group_name': openapi.Schema(type=openapi.TYPE_STRING, description='Имя группы'),
                'permissions_name': openapi.Schema(type=openapi.TYPE_ARRAY,items=openapi.Items(type=openapi.TYPE_STRING), description='Имя права'),
                'change_other_groups': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='изменять другие группы'),
            }
        )
    )
    def post(self, request: Request):
        
        access = False
        group = Group.objects.get(name = request.data['group_name'])
        exp_group = ExpandedGroup.objects.get(group=group)
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4 and exp.group_category==exp_group.category:
                access = True
                break
        if(access or request.user.is_superuser):
            for permission_name in request.data['permissions_name']:
                permission = Permission.objects.get(name = permission_name)
                exp_permission = ExpandedPermission.objects.get(permission=permission)
                group.permissions.remove(permission)
                if(request.data['change_other_groups']):
                        groups = Group.objects.all()
                        for group in groups:
                            expand_group = ExpandedGroup.objects.get(group=group)
                            if(expand_group.level < exp_group.level and exp_group.category == expand_group.category and (group.permissions.contains(permission))):
                                group.permissions.remove(permission)
            group.save()
            return Response(status=status.HTTP_200_OK)
        
#Управление правами
class GetPermissions(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение прав.",
        responses={
            200: "Права получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        }
    )
    def get(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(request.user.is_superuser | access):
            ExpandedPermissions = ExpandedPermission.objects.all()
            permissions_list = []
            if(request.user.is_superuser):
                for expperm in ExpandedPermissions:
                    permission = expperm.permission
                    accession = Accession.objects.get(permission = expperm)
                    if(expperm.permission_mark.id <3):
                        permissions_list.append({'id':permission.id, 'name':permission.name,
                    'category_name':expperm.group_category.name, 'accession_type':expperm.permission_mark.name,
                    'path':accession.path.path, 'component_id':accession.component_id.componentid})
                    elif (expperm.permission_mark.id ==3):
                        permissions_list.append({'id':permission.id, 'name':permission.name,
                    'category_name':expperm.group_category.name, 'accession_type':expperm.permission_mark.name,
                    'path':accession.path.path, 'component_id':''})
                    else:
                        permissions_list.append({'id':permission.id, 'name':permission.name,
                    'category_name':expperm.group_category.name, 'accession_type':expperm.permission_mark.name,
                    'path':'', 'component_id':''})
                result = {"permissions":permissions_list}
            else:
                cat_list=[]
                for exp in exps:
                    if exp.permission_mark.id == 4:
                        cat_list.append(exp.group_category.name)
                for cat in cat_list:                
                    for expperm in ExpandedPermissions:
                        if expperm.group_category.name == cat:
                            permission = expperm.permission
                            accession = Accession.objects.get(permission = expperm)
                            if(expperm.permission_mark.id <3):
                                permissions_list.append({'id':permission.id, 'name':permission.name,
                            'category_name':expperm.group_category.name, 'accession_type':expperm.permission_mark.name,
                            'path':accession.path.path, 'component_id':accession.component_id.componentid})
                            elif (expperm.permission_mark.id ==3):
                                permissions_list.append({'id':permission.id, 'name':permission.name,
                            'category_name':expperm.group_category.name, 'accession_type':expperm.permission_mark.name,
                            'path':accession.path.path, 'component_id':''})
                            else:
                                permissions_list.append({'id':permission.id, 'name':permission.name,
                            'category_name':expperm.group_category.name, 'accession_type':expperm.permission_mark.name,
                            'path':'', 'component_id':''})
                result = {"permissions":permissions_list}
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )

class AddPermission(BaseAPIViewAuthMixin):
     @swagger_auto_schema(
        operation_description="Добавление права",
        responses={
            200: "право добавлено",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
         request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'permission_name': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Имя права'
                ),
                'category_name': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Название категории'
                ),
                'accession_type': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Тип доступа'
                ),
                'path': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Путь доступа'),
                'component_id': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Идентификатор компонента'
                )
            }
        )
    ) 
     def post(self, request: Request):
        access = False
        perms =[]
        pm = PermissionMark.objects.get(name = request.data['accession_type'])
        if(pm.id < 4):
            exps = GetUserExpandedPermissions(request.user)
            for exp in exps:
                if exp.group_category.name == request.data['category_name']:
                    access = True
                    break
            if(access or request.user.is_superuser):
                page = CMSPage.objects.get(path = request.data['path'])
                content_type = ContentType.objects.get_or_create(app_label='cms', model='none')
                categoryy = GroupCategory.objects.get(name = request.data['category_name'])
                permission = Permission.objects.create(name=request.data['permission_name'], content_type_id =content_type[0].id, codename =request.data['permission_name'])
                exp =ExpandedPermission.objects.create(permission = permission,
                permission_mark = pm, group_category = categoryy)
                if(request.data['component_id']!= ''):
                    comp = CMSPageComponent.objects.get(page = page, componentid =request.data['component_id'])
                    Accession.objects.create(permission = exp, path = page, component_id = comp)
                else:
                    Accession.objects.create(permission = exp, path = page)
                return Response(status=status.HTTP_200_OK)
            else:
                return Response(
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            return Response(
                status=status.HTTP_400_BAD_REQUEST
            )

class DeletePermission(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="удаление права",
        responses={
            200: "право удалена",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
         request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'permission_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER, 
                    description='Идентификатор права'
                ),
            }
        )
    )
    def delete(self, request: Request, id):
        permission = Permission.objects.get(id = id )
        expanded_permission = ExpandedPermission.objects.get(permission_id = permission.id)
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4 and exp.group_category == expanded_permission.group_category :
                access = True
                break
        if(access or request.user.is_superuser):
            if (expanded_permission.permission_mark.id < 4):
                accs = Accession.objects.get(permission = expanded_permission)
                accs.delete()
                expanded_permission.delete()
                permission.delete()
                return Response(
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )

class ChangePermission(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="обновление кода права",
        responses={
            200: "код права обновлен",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
         request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'permission_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER, 
                    description='Идентификатор права'
                ),
                'new_permission_name': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Новое имя права'
                ),
                'new_category_name': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Новая категория права'
                ),
                'accession_type': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Тип доступа'
                ),
                'path': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Путь доступа'),
                'component_id': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Идентификатор компонента'
                )
            }
        )
    )
    def put(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4 and exp.group_category.name == request.data['new_category_name'] :
                access = True
                break
        if(request.user.is_superuser | access):
            pm = PermissionMark.objects.get(name = request.data['accession_type'])
            if((pm.id < 4)):
                permission = Permission.objects.get(id = request.data['permission_id'])
                expanded_permission = ExpandedPermission.objects.get(permission = permission)
                category = GroupCategory.objects.get(name = request.data['new_category_name'])
                accs = Accession.objects.get(permission = expanded_permission)
                page = CMSPage.objects.get(path = request.data['path'])
                if(permission.name != request.data['new_permission_name']):
                    permission.name = request.data['new_permission_name']
                    permission.codename = request.data['new_permission_name']
                if(expanded_permission.permission_mark.id != pm.id):
                    expanded_permission.permission_mark = pm
                if(expanded_permission.group_category.name != request.data['new_category_name']):
                    expanded_permission.group_category = category
                if(accs.path.path != request.data['path']):
                    accs.path = page
                if(accs.component_id != request.data['component_id']):
                    if(request.data['component_id'] == ''):
                        accs.component_id = None
                    else:
                        comp = CMSPageComponent.objects.get(page = page, componentid = request.data['component_id'] )
                        accs.component_id = comp
                permission.save()
                expanded_permission.save()
                accs.save()
                return Response(
                    status=status.HTTP_200_OK
                )
            else:
                return Response( 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )

class GetPermissionsByCategory(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение прав по категории",
        responses={
            200: "Права по категории получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
        manual_parameters=[
            openapi.Parameter('category', openapi.IN_QUERY, description="Категория", type=openapi.TYPE_STRING)
        ]
    )
    def get(self, request: Request):
        access = False
        category_name = request.query_params['category']
        category = GroupCategory.objects.get(name = category_name)
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4 and exp.group_category==category:
                access = True
                break
        if(access or request.user.is_superuser):
            expanded_permissions = ExpandedPermission.objects.filter(group_category = category)
            permissions_list = []
            for permission in expanded_permissions:
                perm = permission.permission
                permissions_list.append(perm.name)
            result = {'permissions':permissions_list}
            return Response(
                result,
                status=status.HTTP_200_OK
            )
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)

#Проверка на доступ к компонентам и странице
class CheckAccesstoPage(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение прав пользователя.",
        responses={
            200: "Права пользователя получены",
            401: "Пользователь не авторизован"
        },
        manual_parameters=[
        openapi.Parameter('path', openapi.IN_QUERY, description="Path of page", type=openapi.TYPE_STRING),
    ],
    )
    def get(self, request: Request):
        result = {'access':False}
        if(request.user.is_superuser or (request.query_params.get('path')=='/:pathMatch(.*)*')):
            result['access'] = True
        else:
            try:
                page = CMSPage.objects.get(path = request.query_params.get('path'))
                if(page.liminationtype != 'closepage'):  
                    result['access'] = True
                else:
                    id = request.user.id
                    groups = Group.objects.filter(user = id)
                    permisson_list = []
                    for group in groups:
                        perms = Permission.objects.filter(group = group)
                        for perm in perms:
                            permisson_list.append(perm)
                    perms = Permission.objects.filter(user = id)
                    for perm in perms:
                        permisson_list.append(perm)
                    for perm in permisson_list:
                        expanded_permission = ExpandedPermission.objects.get(permission_id = perm.id)
                        accession = Accession.objects.get(permission = expanded_permission)
                        if(accession.path == page and expanded_permission.permission_mark.id == 3):
                            result['access'] = True
                            break
            except:
                result['access'] = True
        return Response(
            result,
            status=status.HTTP_200_OK
        )

class CheckAccessToComponents(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение прав доступа к компоненту",
        responses={
            200: "Права доступа к компоненту получены",
            401: "Пользователь не авторизован"
        },
        manual_parameters=[
        openapi.Parameter('path', openapi.IN_QUERY, description="Путь страницы", type=openapi.TYPE_STRING),
    ],
    )
    def get(self, request: Request):
        result = []
        try:
            page = CMSPage.objects.get(path = request.query_params.get('path'))
            comps = CMSPageComponent.objects.filter(page=page)
            for comp in comps:
                result.append({'component':comp.componentid,'read':False,'write':False })
            if(request.user.is_superuser):
                for res in result:
                    res['read'] = True
                    res['write'] = True
            else:
                groups = Group.objects.filter(user =request.user)
                permisson_list = []
                for group in groups:
                    perms = Permission.objects.filter(group = group)
                    for perm in perms:
                        permisson_list.append(perm)
                perms = Permission.objects.filter(user = request.user)
                for perm in perms:
                    permisson_list.append(perm)
                for perm in permisson_list: 
                    expanded_permission = ExpandedPermission.objects.get(permission = perm)
                    pm = expanded_permission.permission_mark
                    if(pm.name!='PageAccession'):
                        accession = Accession.objects.get(permission = expanded_permission)
                        if(accession.path == page and accession.component_id!=None):
                            for r in result:
                                if(r['component']== accession.component_id.componentid):
                                    if(pm.name=='ComponentAccessionToRead'):
                                        r['read'] = True
                                    elif(pm.name=='ComponentAccessionToReadAndWrite'):
                                        r['read'] = True
                                        r['write'] = True
            return Response(
                result,
                status=status.HTTP_200_OK
            )
        except CMSPageComponent.DoesNotExist:
            return Response({'details':'Данной страницы нет в базе данных ограничений'}, status=status.HTTP_404_NOT_FOUND)
        except CMSPageComponent.DoesNotExist:
            return Response({'details':'У данной страницы нет ограничений на компоненты'}, status=status.HTTP_404_NOT_FOUND)
        except:        
            return Response(
            result,
            status=status.HTTP_200_OK
        )

class CheckAccessToAdminPanel(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение прав доступа к панели администратора",
        responses={
            200: "Права доступа к панели администратора получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
    )
    def get(self, request: Request):
        result = {'access_to_panel':False, 'access_to_category':False}
        perms =[]
        if(request.user.is_superuser):
            result['access_to_panel'] = True
            result['access_to_category'] =True
        else:
            user = request.user
            groups = user.groups.all()
            for group in groups:
                permissions = group.permissions.all()
                for permission in permissions:
                    expanded_permission = ExpandedPermission.objects.get(permission = permission)
                    if(expanded_permission.permission_mark.id == 4):
                        result['access_to_panel'] = True
                        break
            if(result['access_to_panel'] == False):
                permissions = user.user_permissions.all()
                for permission in permissions:
                    expanded_permission = ExpandedPermission.objects.get(permission = permission)
                    if(expanded_permission.permission_mark.id == 4):
                        result['access_to_panel'] = True
                        break
        return Response(
            result,
            status=status.HTTP_200_OK
        )

#Работа с пользователями
class GetUserGroupsAndPermissions(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение групп и прав пользователя",
        responses={
            200: "Группы и права пользователя получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
    )
    def get(self, request: Request):
        access = False
        ugplist = []
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
        if(access or request.user.is_superuser):
            if(request.user.is_superuser): 
                users = User.objects.all()
                for user in users:
                    groups = user.groups.all()
                    groups_user = []
                    if(len(groups) > 0):
                        for group in groups:
                            groups_user.append(group.name)
                    perms = user.user_permissions.all()
                    user_perms = []
                    if(len(perms) > 0):
                        for perm in perms:
                            user_perms.append(perm.name)
                    tmpdict = {'user_id':user.id,'user': user.username, "groups":groups_user,"permissions":user_perms}
                    ugplist.append(tmpdict)
                result = {'users':ugplist}
            else:
                catlist =[]
                for exp in exps:
                    if(exp.permission_mark.id==4):
                        catlist.append(exp.group_category)
                users = User.objects.all()
                for user in users:
                    groups = user.groups.all()
                    groups_user = []
                    if(len(groups) > 0):
                        for group in groups:
                            exp_group = ExpandedGroup.objects.get(group=group)
                            for cat in catlist:
                                if(exp_group.category==cat):
                                    groups_user.append(group.name)
                    perms = user.user_permissions.all()
                    user_perms = []
                    if(len(perms) > 0):
                        for perm in perms:
                            exp_perm = ExpandedPermission.objects.get(permission =perm)
                            for cat in catlist:
                                if(exp_perm.group_category == cat):
                                    user_perms.append(perm.name)
                    tmpdict = {'user_id':user.id,'user': user.username, "groups":groups_user,"permissions":user_perms}
                    ugplist.append(tmpdict)
                result = {'users':ugplist}
            return Response(
                result,
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )

class AddUserGroup(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Добавление пользователя в группу",
        responses={
            200: "Пользователь добавлен в группу",
            401: "Пользователь не авторизован",
            403: "Нет доступа"  
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING, description='Имя пользователя'),
                'groups_name': openapi.Schema(type=openapi.TYPE_ARRAY,items=openapi.Items(type=openapi.TYPE_STRING), description='Имя группы')
            }
        )
    )
    def post(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(access or request.user.is_superuser):
            if(request.user.is_superuser):
                user = User.objects.get(username = request.data['username'])
                for group_name in request.data['groups_name']:
                    group = Group.objects.get(name = group_name)
                    user.groups.add(group)
                user.save()
            else:
                catlist =[]
                for exp in exps:
                    if(exp.permission_mark.id==4):
                        catlist.append(exp.group_category)
                user = User.objects.get(username = request.data['username'])
                for group_name in request.data['groups_name']:
                    group = Group.objects.get(name = group_name)
                    exp_group = ExpandedGroup.objects.get(group=group)
                    cat_checked = False
                    for cat in catlist:
                        if(cat == exp_group.category):
                            cat_checked = True
                    if(cat_checked):
                        user.groups.add(group)
                    else:
                        return Response(status=status.HTTP_403_FORBIDDEN)
                user.save()
        return Response(status=status.HTTP_200_OK)  

class RemoveUserGroup(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Удаление пользователя из группы",
        responses={
            200: "Пользователь удален из группы",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_STRING, description='id пользователя'),
                'groups_name': openapi.Schema(type=openapi.TYPE_ARRAY,items=openapi.Items(type=openapi.TYPE_STRING), description='Имя группы')
            }
        )
    )
    def post(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(access or request.user.is_superuser):
            user = User.objects.get(id = request.data['user_id'])
            if(request.user.is_superuser):
                for group_name in request.data['groups_name']:
                    group = Group.objects.get(name = group_name)
                    user.groups.remove(group)
                user.save()
            else :
                catlist =[]
                for exp in exps:
                    if(exp.permission_mark.id==4):
                        catlist.append(exp.group_category)
                for group_name in request.data['groups_name']:
                    group = Group.objects.get(name = group_name)
                    exp_group = ExpandedGroup.objects.get(group=group)
                    cat_checked = False
                    for cat in catlist:
                        if(cat == exp_group.    category):
                            cat_checked = True
                    if(cat_checked):
                        user.groups.remove(group)
                    else:
                        return Response(status=status.HTTP_403_FORBIDDEN)
                user.save()
        return Response(status=status.HTTP_200_OK)   
    
class RemoveUserPermission(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Удаление права пользователя",
        responses={
            200: "Право удалено пользователю",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_STRING, description='id пользователя'),
                'permissions_name': openapi.Schema(type=openapi.TYPE_ARRAY,items=openapi.Items(type=openapi.TYPE_STRING), description='Имя права')
            }
        )
    )
    def post(self, request: Request):     
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(access or request.user.is_superuser):
            user = User.objects.get(id = request.data['user_id'])
            if(request.user.is_superuser):
                for permission_name in request.data['permissions_name']:
                    permission = Permission.objects.get(name = permission_name)
                    user.user_permissions.remove(permission)
            else:
                catlist =[]
                for exp in exps:
                    if(exp.permission_mark.id==4):
                        catlist.append(exp.group_category)
                for permission_name in request.data['permissions_name']:
                    permission = Permission.objects.get(name = permission_name)
                    exp_permission = ExpandedPermission.objects.get(permission=permission)
                    cat_acc = False
                    for cat in catlist:
                        if(cat == exp_permission.group_category):
                            cat_acc = True
                    if(cat_acc):
                        user.user_permissions.remove(permission)
                    else:
                        return Response(status=status.HTTP_400_BAD_REQUEST)
            user.save()
            return Response(status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)
        
class AddUserPermission(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Добавление права пользователю",
        responses={
            200: "Право добавлено пользователю",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING, description='Имя пользователя'),
                'permissions_name': openapi.Schema(type=openapi.TYPE_ARRAY,items=openapi.Items(type=openapi.TYPE_STRING), description='Имя права')
            }
        )
    )
    def post(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(access or request.user.is_superuser):
            user = User.objects.get(username = request.data['username'])
            if(request.user.is_superuser):
                for permission_name in request.data['permissions_name']:
                    permission = Permission.objects.get(name = permission_name)
                    user.user_permissions.add(permission)
                user.save()
            else:
                catlist =[]
                for exp in exps:
                    if(exp.permission_mark.id==4):
                        catlist.append(exp.group_category)
                for permission_name in request.data['permissions_name']:
                    permission = Permission.objects.get(name = permission_name)
                    exp_permission = ExpandedPermission.objects.get(permission=permission)
                    cat_acc = False
                    for cat in catlist:
                        if(cat == exp_permission.group_category):
                            cat_acc = True
                    if(cat_acc):
                        user.user_permissions.add(permission)
                    else:
                        return Response(status=status.HTTP_400_BAD_REQUEST)
                user.save()
            return Response(status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)

#Работа с текущим пользователем    
class GetUserName(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение имен пользователей",
        responses={
            200: "Имена пользователей получены",
            401: "Пользователь не авторизован",
        },
    )
    def get(self, request: Request):
        user = request.user
        return Response(
            user.username,
            status=status.HTTP_200_OK
        )

class GetGroupsByCategory(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение групп пользователя",
        responses={
            200: "Группы пользователя",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
    )
    def get(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(access or request.user.is_superuser):
            groups_list = []
            groups = Group.objects.all()
            if(request.user.is_superuser):
                for group in groups:
                    groups_list.append(group.name)
            else:
                cats = []
                for exp in exps:
                    if exp.permission_mark.id == 4:
                        cats.append(exp.group_category)
                for group in groups:
                    exp_group = ExpandedGroup.objects.get(group=group)
                    for cat in cats:
                        if(exp_group.category == cat):
                            groups_list.append(group.name)
            result = {'groups':groups_list}
            return Response(
                result,
                status=status.HTTP_200_OK
            )
        else:
            return Response(status= status.HTTP_403_FORBIDDEN)
        
class GetUserPermissions(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение прав пользователя",
        responses={
            200: "Права пользователя",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        },
    )
    def get(self, request: Request):
        permissions = Permission.objects.all()
        permissions_list = []
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(access or request.user.is_superuser):
            if(request.user.is_superuser):
                for permission in permissions:
                    permissions_list.append(permission.name)
            else:
                cats = []
                for exp in exps:
                    if exp.permission_mark.id == 4:
                        cats.append(exp.group_category)
                for permission in permissions:
                    exp_permission = ExpandedPermission.objects.get(permission=permission)
                    for cat in cats:
                        if(exp_permission.group_category == cat):
                            permissions_list.append(permission.name)
            result = {'permissions':permissions_list}
            return Response(
                result,
                status=status.HTTP_200_OK
            )
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)
    
#Работа со страницами и компонентами
class PatchAllProgectPages(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description='Получение и обновление всех путей проекта из файла маршрутов, исключая mainRoutes',
        responses={
            200: "Пути получены и обновлены",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
            400: "Ошибка чтения файла маршрутов"
        },
    )
    def post(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(request.user.is_superuser | access):
            try:
                # Получаем все клиентские маршруты (core + внешние модули)
                client_routes_index = _discover_client_routes_index()
                normalized_paths = set(client_routes_index.keys())

                # Нормализуем и обновляем существующие пути в CMSPage,
                # чтобы избавиться от дубликатов вида '/path' и '/path/'.
                for path in normalized_paths:
                    normalized = _normalize_path(path)
                    # Ищем существующие записи с нормализованным путём или тем же путём c завершающим слешем
                    candidates = CMSPage.objects.filter(path__in=[normalized, f'{normalized}/'])
                    if candidates.exists():
                        # Оставляем первую запись с нормализованным путём
                        main_page = candidates.first()
                        if main_page.path != normalized:
                            main_page.path = normalized
                            main_page.save(update_fields=['path'])
                        # Удаляем остальные дубликаты, если есть
                        candidates.exclude(pk=main_page.pk).delete()
                    else:
                        CMSPage.objects.create(path=normalized)

                return Response(
                    sorted(normalized_paths),
                    status=status.HTTP_200_OK
                )

            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )


class GetCMSPages(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение всех страниц CMS",
        responses={
            200: "Страницы получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        }
    )
    def get(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break

        if request.user.is_superuser | access:
            # Формируем индекс path -> module_name из клиентских маршрутов (core + внешние модули)
            path_to_module = _discover_client_routes_index()

            pages = CMSPage.objects.all()
            pages_list = []
            for page in pages:
                normalized_path = _normalize_path(page.path)
                module_name = path_to_module.get(normalized_path, 'core')
                pages_list.append(
                    {
                        'id': page.id,
                        'path': page.path,
                        'type': page.liminationtype,
                        'module_name': module_name,
                    }
                )

            return Response(
                {'pages': pages_list},
                status=status.HTTP_200_OK
            )

        return Response(
            status=status.HTTP_403_FORBIDDEN
        )

class UpdatePageLiminationType(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Обновление типа доступа страницы CMS",
        responses={
            200: "Страница обновлена",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
            400: "Неверные данные"
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'path': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Путь страницы'
                ),
                'limination_type': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Новый тип доступа'
                )
            }
        )
    )
    def put(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(request.user.is_superuser | access):
            try:
                page = CMSPage.objects.get(path=request.data['path'])
                page.liminationtype = request.data['limination_type']
                page.save()
                return Response(
                    status=status.HTTP_200_OK
                )
            except CMSPage.DoesNotExist:
                return Response(
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )
        
class AddPageComponent(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Добавление компонента к странице",
        responses={
            200: "Компонент добавлен",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
            400: "Неверные данные"
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'path': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Путь страницы'
                ),
                'component_id': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='ID компонента'
                )
            }
        )
    )
    def post(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(request.user.is_superuser | access):
            try:
                
                page = CMSPage.objects.get(path=request.data['path'])
                
                # Проверяем существование компонента более детально
                existing_components = CMSPageComponent.objects.filter(
                    page=page,
                    componentid=request.data['component_id']
                )
                if existing_components.exists():
                    return Response(
                        {
                            'error': 'Такой компонент уже существует на странице',
                            'debug_info': {
                                'component_id': request.data['component_id'],
                                'page_path': page.path,
                                'found_components': list(existing_components.values('id', 'componentid', 'page__path'))
                            }
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Создаем новую запись CMSPageComponent
                CMSPageComponent.objects.create(
                    page = page,
                    componentid=request.data['component_id']
                )
                
                return Response(
                    {'message': 'Компонент успешно добавлен'},
                    status=status.HTTP_200_OK
                )
            except CMSPage.DoesNotExist:

                return Response(
                    {'error': 'Страница не найдена'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )

class RemovePageComponent(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Удаление компонента со страницы",
        responses={
            200: "Компонент удален",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
            400: "Неверные данные"
        },
        manual_parameters=[
            openapi.Parameter('path', openapi.IN_QUERY, description="Путь страницы", type=openapi.TYPE_STRING),
            openapi.Parameter('component_id', openapi.IN_QUERY, description="ID компонента", type=openapi.TYPE_STRING)
        ]
    )
    def delete(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(request.user.is_superuser | access):
            try:
                page = CMSPage.objects.get(path=request.query_params.get('path'))
                component = CMSPageComponent.objects.get(
                    page = page,
                    componentid=request.query_params.get('component_id')
                )
                if(len(Accession.objects.filter(component_id=component))==0):
                    component.delete()
                    return Response(
                        {'message': 'Компонент успешно удален'},
                        status=status.HTTP_200_OK
                    )
                else:
                    return Response(
                        {'message': 'Нельзя удалить компонент, пока он связан с правами'},
                        status=status.HTTP_200_OK
                    )
                
            except CMSPageComponent.DoesNotExist:
                return Response(
                    {'error': 'Компонент не найден на странице'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except CMSPage.DoesNotExist:
                return Response(
                    {'error': 'Страница не найдена'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )

class UpdatePageComponent(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Изменение ID компонента на странице",
        responses={
            200: "Компонент обновлен",
            401: "Пользователь не авторизован",
            403: "Нет доступа",
            400: "Неверные данные"
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'path': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Путь страницы'
                ),
                'old_component_id': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Старый ID компонента'
                ),
                'new_component_id': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Новый ID компонента'
                )
            }
        )
    )
    def put(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(request.user.is_superuser | access):
            try:
                page = CMSPage.objects.get(path=request.data['path'])
                # Проверяем существование компонента для изменения
                component = CMSPageComponent.objects.get(
                    page = page,
                    componentid=request.data['old_component_id']
                )
                
                # Проверяем, не существует ли уже компонент с новым ID
                if CMSPageComponent.objects.filter(
                    page = page,
                    componentid=request.data['new_component_id']
                ).exists():
                    return Response(
                        {'error': 'Компонент с таким ID уже существует на странице'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Обновляем ID компонента
                component.componentid = request.data['new_component_id']
                component.save()
                
                return Response(
                    {'message': 'ID компонента успешно обновлен'},
                    status=status.HTTP_200_OK
                )
            except CMSPageComponent.DoesNotExist:
                return Response(
                    {'error': 'Компонент не найден на странице'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )

class GetPageComponents(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение всех компонентов страниц",
        responses={
            200: "Компоненты получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        }
    )
    def get(self, request: Request):
        access = False
        exps = GetUserExpandedPermissions(request.user)
        for exp in exps:
            if exp.permission_mark.id == 4:
                access = True
                break
        if(request.user.is_superuser | access):
            components = CMSPageComponent.objects.all()
            components_list = []
            for component in components:
                components_list.append({
                    'id': component.componentid,
                    'page_path': component.page.path,
                })
            return Response(
                {'components': components_list},
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN
            )
        
class GetClosedPagesForUser(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение закрытых страниц CMS, к которым у пользователя нет доступа",
        responses={
            200: "Закрытые страницы получены",
            401: "Пользователь не авторизован",
            403: "Нет доступа"
        }
    )
    def get(self, request: Request):
        if request.user.is_superuser:
            return Response(
                {'pages': []},
                status=status.HTTP_200_OK
            )
        else:
            all_closed_pages = CMSPage.objects.filter(liminationtype='closepage')
            user_permissions = []
            user_groups = request.user.groups.all()
            for group in user_groups:
                group_permissions = group.permissions.all()
                user_permissions.extend(group_permissions)
            personal_permissions = request.user.user_permissions.all()
            user_permissions.extend(personal_permissions)
            accessible_pages = set()
            for permission in user_permissions:
                try:
                    expanded_permission = ExpandedPermission.objects.get(permission=permission)
                    accession = Accession.objects.get(permission=expanded_permission)
                    if accession.path:
                        accessible_pages.add(accession.path.path)
                except (ExpandedPermission.DoesNotExist, Accession.DoesNotExist):
                    continue
            inaccessible_closed_pages = []
            for page in all_closed_pages:
                if page.path not in accessible_pages:
                    inaccessible_closed_pages.append({
                        'id': page.id,
                        'path': page.path,
                        'type': page.liminationtype
                    })
            
            return Response(
                {'pages': inaccessible_closed_pages},
                status=status.HTTP_200_OK
            )
