from django.db import models
from django.contrib.auth.models import (User, Group, Permission)
from django.utils import timezone

PageChoicese =[
    ('withliminations','Страница с ограничениями'),
    ('withoutliminations','Страница без ограничений'),
    ('closepage', 'Закрытая страница')
]

class Review(models.Model):
    author_id = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField(default='')
    rating = models.IntegerField(default=0)

class GroupURL(models.Model):
    url = models.CharField(max_length=255, default='')
    group_id = models.ForeignKey(Group, on_delete=models.CASCADE)
    class Meta:
        default_permissions = ()

class PermissionMark(models.Model):
    name = models.CharField(max_length=255, default='')

class Object_Type(models.Model):
    name = models.CharField(max_length=100, default='')
    
class Object(models.Model):
    objectlink = models.CharField(max_length=255, default='')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.ForeignKey(Object_Type, on_delete=models.CASCADE)

class GroupCategory(models.Model):
    name = models.CharField(max_length=255, default='')

class ExpandedPermission(models.Model):
    permission = models.OneToOneField(Permission, on_delete=models.CASCADE)
    permission_mark = models.ForeignKey(PermissionMark, on_delete=models.CASCADE)   
    group_category = models.ForeignKey(GroupCategory, on_delete=models.CASCADE)

class CMSPage(models.Model):
    path = models.CharField(max_length=255, default='')
    liminationtype = models.CharField(max_length=255,choices=PageChoicese, default='withoutliminations')

class CMSPageComponent(models.Model):
    componentid = models.CharField(max_length=255, default='')
    page = models.ForeignKey(CMSPage, on_delete=models.CASCADE, unique=False)

class Accession(models.Model):
    path = models.ForeignKey(CMSPage, on_delete=models.CASCADE, null=True )
    component_id = models.ForeignKey(CMSPageComponent, on_delete=models.CASCADE, null=True)
    permission = models.ForeignKey(ExpandedPermission, on_delete=models.CASCADE, default=0)

class ExpandedGroup(models.Model):
    group = models.OneToOneField(Group, on_delete=models.CASCADE)
    category = models.ForeignKey(GroupCategory, on_delete=models.CASCADE)
    level = models.IntegerField(default=0)