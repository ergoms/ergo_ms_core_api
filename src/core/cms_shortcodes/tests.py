from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.test.utils import override_settings

from .models import CmsPage, CmsShortcodeTemplate, CmsShortcodeInstance

@override_settings(ROOT_URLCONF="src.config.urls")
class CmsApiTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')

        # Получаем JWT токен
        refresh = RefreshToken.for_user(self.user)
        self.access_token = str(refresh.access_token)

        # Устанавливаем заголовок авторизации
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')

        self.template = CmsShortcodeTemplate.objects.create(
            name='Test Button',
            component_type='button',
            class_list=['btn', 'btn-primary'],
            extra_data={"text": "Нажми меня"},
            creator=self.user,
        )

    def test_create_page(self):
        response = self.client.post('/cms_shortcodes/pages/', {
            'name': 'Главная',
            'slug': 'home'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CmsPage.objects.count(), 1)

    def test_create_instance(self):
        page = CmsPage.objects.create(name='Главная', slug='home', creator=self.user)
        response = self.client.post('/cms_shortcodes/instances/', {
            'template': self.template.id,
            'page': page.id,
            'parent': None,
            'class_list': ['mb-3'],
            'extra_data': {'text': 'Привет'},
            'position': 0
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CmsShortcodeInstance.objects.count(), 1)

    def test_get_page_with_instances(self):
        page = CmsPage.objects.create(name='Главная', slug='home', creator=self.user)
        CmsShortcodeInstance.objects.create(
            template=self.template,
            page=page,
            class_list=['mb-2'],
            extra_data={"text": "Вложенный"},
            position=0
        )
        response = self.client.get(f'/cms_shortcodes/pages/{page.slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('instances', response.data)
        self.assertEqual(len(response.data['instances']), 1)

    def test_get_templates(self):
        response = self.client.get('/cms_shortcodes/templates/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

@override_settings(ROOT_URLCONF="src.config.urls")
class CmsNestedShortcodesTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='nesteduser', password='testpass')
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

        self.template = CmsShortcodeTemplate.objects.create(
            name='Container Template',
            component_type='container',
            class_list=['container'],
            extra_data={},
            creator=self.user,
            is_active=True
        )

        self.page = CmsPage.objects.create(
            name='Nested Page',
            slug='nested-page',
            creator=self.user,
        )

    def test_create_nested_instance(self):
        parent_instance = CmsShortcodeInstance.objects.create(
            template=self.template,
            page=self.page,
            class_list=['parent'],
            extra_data={"text": "parent"},
            position=0
        )

        response = self.client.post('/cms_shortcodes/instances/', {
            'template': self.template.id,
            'page': self.page.id,
            'parent': parent_instance.id,
            'class_list': ['child'],
            'extra_data': {'text': 'child'},
            'position': 1
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CmsShortcodeInstance.objects.count(), 2)
        child = CmsShortcodeInstance.objects.get(position=1)
        self.assertEqual(child.parent.id, parent_instance.id)

    def test_page_with_nested_instances(self):
        parent = CmsShortcodeInstance.objects.create(
            template=self.template,
            page=self.page,
            class_list=['outer'],
            extra_data={},
            position=0
        )
        CmsShortcodeInstance.objects.create(
            template=self.template,
            page=self.page,
            parent=parent,
            class_list=['inner'],
            extra_data={"nested": True},
            position=0
        )

        response = self.client.get(f'/cms_shortcodes/pages/{self.page.slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        top_level = [i for i in response.data['instances'] if i['parent'] is None]
        self.assertEqual(len(top_level), 1)
        self.assertEqual(len(top_level[0]['children']), 1)