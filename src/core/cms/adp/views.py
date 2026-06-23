from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.serializers import ValidationError as DRFValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from django.contrib.auth import authenticate
from django.utils.crypto import get_random_string
import re

from src.core.utils.methods import (
    parse_errors_to_dict, 
    send_confirmation_email,
)
from src.core.cms.adp.models import EmailConfirmationCode, UserDevice, UserProfile
from src.core.cms.adp.serializers import (
    UserLoginSerializer, 
    UserRegistrationSerializer,
    UserRegistrationValidationSerializer,
    ChangePasswordSerializer,
    UserDeviceSerializer,
    CMSUserSerializer,
    CMSUserBasicSerializer,
    CMSUserMenuSerializer,
    CMSUserProfileSerializer,
    UpdateUserProfileSerializer,
)
from src.core.utils.base.base_views import BaseAPIView, BaseAPIViewAuthMixin

from django.contrib.auth.models import User
import logging

from src.core.cms.adp.password_policy import validate_new_password_pair
from src.core.utils.database.main import OrderedDictQueryExecutor
from src.config.settings.auth import get_token_lifetime

logger = logging.getLogger(__name__)

class UserRegistrationValidationView(BaseAPIView):
    @swagger_auto_schema(
        operation_description="Регистрация нового пользователя.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,

            properties={
                'first_name': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Имя'
                ),
                'username': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Логин'
                ),
                'email': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    format=openapi.FORMAT_EMAIL, 
                    description='Электронная почта'
                ),
                'password': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    format=openapi.FORMAT_PASSWORD, 
                    description='Пароль'
                ),
                'password_confirm': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    format=openapi.FORMAT_PASSWORD, 
                    description='Подтверждение пароля'
                ),
            },

            required=['first_name', 'username', 'email', 'password', 'password_confirm'],
        ),
        responses={
            201: "Пользователь успешно зарегистрирован.",
            400: "Регистрация не успешна."
        },
    )
    def post(self, request):
        serializer = UserRegistrationValidationSerializer(data=request.data)
        
        #Command.handle('createsuperuser',username='myusername', email='myemail@example.com', password='mypassword')
        
        if serializer.is_valid():
            #User.objects.create_user(username=serializer.field_name, email= serializer.email, password= serializer.password, is_superuser=True).save()
            successful_response = Response(
                {"message": "Валидация успешна."}, 
                status=status.HTTP_200_OK
            )
            return successful_response
        
        errors = parse_errors_to_dict(serializer.errors)
        return Response(
            errors, 
            status=status.HTTP_400_BAD_REQUEST
        )

class SendConfirmationCodeView(BaseAPIView):
    @swagger_auto_schema(
        operation_description="Отправка кода подтверждения.",
    )   
    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"error": "Отсутствует Email"}, status=status.HTTP_400_BAD_REQUEST)

        # Проверяем существование пользователя с указанным email
        try:
            User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Пользователь с таким email не найден"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Генерация 6-значного кода
        code = get_random_string(length=6, allowed_chars='0123456789')
        
        # Обновляем или создаём запись для email
        EmailConfirmationCode.objects.update_or_create(
            email=email,
            defaults={"code": code},
        )
        
        # Отправляем email
        success, error_message = send_confirmation_email(email, code)
        
        if not success:
            return Response(
                {
                    "error": "Не удалось отправить email. Проверьте настройки SMTP.",
                    "detail": error_message
                }, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response({"message": "Код подтверждения отправлен"}, status=status.HTTP_200_OK)

class VerifyConfirmationCodeView(BaseAPIView):
    @swagger_auto_schema(
        operation_description="Проверка кода подтверждения.",
    )
    def post(self, request):
        email = request.data.get("email")
        code = request.data.get("code")


        if not email or not code:
            return Response({"error": "Email и код обязательны"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            confirmation_code = EmailConfirmationCode.objects.get(email=email)
        except EmailConfirmationCode.DoesNotExist:
            return Response({"error": "Неверный Email или код"}, status=status.HTTP_400_BAD_REQUEST)

        if confirmation_code.code == code:
            # Код верен, можно выполнить дальнейшие действия
            # Удаляем запись после успешной проверки
            confirmation_code.delete()
            return Response({"message": "Код успешно подтвержден"}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Неверный код"}, status=status.HTTP_400_BAD_REQUEST)

class ResetPasswordView(BaseAPIView):
    @swagger_auto_schema(
        operation_description="Сброс пароля по коду подтверждения.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_EMAIL,
                    description='Email пользователя'
                ),
                'code': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Код подтверждения'
                ),
                'new_password': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_PASSWORD,
                    description='Новый пароль'
                ),
                'confirm_password': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_PASSWORD,
                    description='Подтверждение нового пароля'
                ),
            },
            required=['email', 'code', 'new_password', 'confirm_password'],
        ),
        responses={
            200: "Пароль успешно изменён.",
            400: "Ошибка валидации данных."
        },
    )
    def post(self, request):
        email = request.data.get("email")
        code = request.data.get("code")
        new_password = request.data.get("new_password")
        confirm_password = request.data.get("confirm_password")

        if not email or not code or not new_password or not confirm_password:
            return Response(
                {"error": "Все поля обязательны для заполнения"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_new_password_pair({
                'new_password': new_password,
                'confirm_password': confirm_password,
            })
        except DRFValidationError as exc:
            detail = exc.detail
            if isinstance(detail, list):
                error_message = str(detail[0])
            elif isinstance(detail, dict):
                first_value = next(iter(detail.values()))
                error_message = str(first_value[0] if isinstance(first_value, list) else first_value)
            else:
                error_message = str(detail)
            return Response(
                {'error': error_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Проверяем код подтверждения
        try:
            confirmation_code = EmailConfirmationCode.objects.get(email=email)
        except EmailConfirmationCode.DoesNotExist:
            return Response(
                {"error": "Неверный Email или код"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        if confirmation_code.code != code:
            return Response(
                {"error": "Неверный код"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Проверяем существование пользователя
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Пользователь с таким email не найден"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Устанавливаем новый пароль
        user.set_password(new_password)
        user.save()

        # Удаляем использованный код
        confirmation_code.delete()

        return Response(
            {"message": "Пароль успешно изменён"}, 
            status=status.HTTP_200_OK
        )
        
class UserRegistrationView(BaseAPIView):
    @swagger_auto_schema(
        operation_description="Проверка регистрации.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,

            properties={
                'first_name': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Имя'
                ),
                'username': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Логин'
                ),
                'email': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    format=openapi.FORMAT_EMAIL, 
                    description='Электронная почта'
                ),
                'password': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    format=openapi.FORMAT_PASSWORD, 
                    description='Пароль'
                ),
                'password_confirm': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    format=openapi.FORMAT_PASSWORD, 
                    description='Подтверждение пароля'
                ),
            },

            required=['first_name', 'username', 'email', 'password', 'password_confirm'],
        ),
        responses={
            201: "Пользователь успешно зарегистрирован.",
            400: "Регистрация не успешна."
        },
    )
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()

            successful_response = Response(
                {
                    "message": "Регистрация успешна.",
                    "user_id": user.id,
                    "username": user.username
                }, 
                status=status.HTTP_201_CREATED
            )
            return successful_response

        errors = parse_errors_to_dict(serializer.errors)
        return Response(
            errors, 
            status=status.HTTP_400_BAD_REQUEST
        )

class UserAuthorizationView(BaseAPIView):
    @swagger_auto_schema(
        operation_description="Авторизация пользователя.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'username': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Логин'
                ),
                'password': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_PASSWORD,
                    description='Пароль'
                ),
                'remember_me': openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    description='Запомнить меня (увеличенное время жизни токенов)',
                    default=False
                ),
            },
            required=['username', 'password'],
        ),
            responses={
                200: openapi.Response(
                    description="Пользователь успешно авторизован.",
                    examples={
                        "application/json": {
                            "refresh": "your_refresh_token",
                            "access": "your_access_token"
                        }
                    }
                ),
                400: "Авторизация не успешна."
            },
    )
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)

        if serializer.is_valid():
            username = serializer.validated_data['username']
            password = serializer.validated_data['password']
            remember_me = request.data.get('remember_me', False)

            user = authenticate(request, username=username, password=password)

            if user is not None:
                # Создаем или обновляем информацию об устройстве
                self._create_or_update_device(request, user)
                
                # Получаем время жизни токенов в зависимости от remember_me
                access_lifetime, refresh_lifetime = get_token_lifetime(remember_me)
                
                # Создаем токены с кастомным временем жизни
                refresh = RefreshToken.for_user(user)
                refresh.set_exp(lifetime=refresh_lifetime)
                
                # ВАЖНО: сохраняем access_token в переменную, т.к. каждое обращение
                # к refresh.access_token создаёт новый токен с дефолтным временем
                access_token = refresh.access_token
                access_token.set_exp(lifetime=access_lifetime)
                
                return Response(
                    {
                        'refresh': str(refresh),
                        'access': str(access_token)
                    },
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {
                        "message": "Неверные учетные данные."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        errors = parse_errors_to_dict(serializer.errors)
        return Response(
            errors,
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def _create_or_update_device(self, request, user):
        """Создает или обновляет информацию об устройстве пользователя"""
        ip_address = self._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        device_type = self._detect_device_type(user_agent)
        device_name = self._get_device_name(user_agent, device_type)
        
        # Ищем существующее устройство по пользователю и IP
        try:
            device = UserDevice.objects.get(user=user, ip_address=ip_address)
            # Обновляем существующее устройство
            device.is_active = True
            device.user_agent = user_agent
            device.device_name = device_name
            device.device_type = device_type
            device.save()
        except UserDevice.DoesNotExist:
            # Создаем новое устройство
            device = UserDevice.objects.create(
                user=user,
                ip_address=ip_address,
                device_type=device_type,
                device_name=device_name,
                user_agent=user_agent,
                city='Неизвестно',  # Можно добавить геолокацию позже
                country='Неизвестно',
                is_active=True,
            )
    
    def _get_client_ip(self, request):
        """Получает IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _detect_device_type(self, user_agent):
        """Определяет тип устройства по User-Agent"""
        user_agent = user_agent.lower()
        
        if 'mobile' in user_agent or 'android' in user_agent or 'iphone' in user_agent:
            return 'mobile'
        elif 'tablet' in user_agent or 'ipad' in user_agent:
            return 'tablet'
        elif 'macintosh' in user_agent or 'mac os' in user_agent:
            return 'laptop'
        elif 'windows' in user_agent or 'linux' in user_agent:
            return 'desktop'
        else:
            return 'desktop'  # По умолчанию
    
    def _get_device_name(self, user_agent, device_type):
        """Получает название устройства по User-Agent"""
        user_agent = user_agent.lower()
        
        if 'windows' in user_agent:
            return 'Windows PC'
        elif 'macintosh' in user_agent or 'mac os' in user_agent:
            return 'Mac'
        elif 'linux' in user_agent:
            return 'Linux PC'
        elif 'android' in user_agent:
            return 'Android Device'
        elif 'iphone' in user_agent:
            return 'iPhone'
        elif 'ipad' in user_agent:
            return 'iPad'
        else:
            device_names = {
                'mobile': 'Mobile Device',
                'tablet': 'Tablet',
                'laptop': 'Laptop',
                'desktop': 'Desktop'
            }
            return device_names.get(device_type, 'Unknown Device')

class UserMenuView(BaseAPIViewAuthMixin):
    """
    Легковесный endpoint для получения минимальных данных пользователя для меню.
    Возвращает только username, email, full_name, initials_name.
    """
    @swagger_auto_schema(
        operation_description="Получение минимальных данных пользователя для отображения в меню.",
        responses={
            200: openapi.Response(
                description="Минимальные данные пользователя для меню.",
                schema=CMSUserMenuSerializer()
            ),
        },
        security=[{'Bearer': []}]
    )
    def get(self, request):
        # Обновляем последнюю активность текущего устройства
        self._update_device_activity(request)
        
        serializer = CMSUserMenuSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def _update_device_activity(self, request):
        """Обновляет последнюю активность устройства пользователя"""
        try:
            ip_address = self._get_client_ip(request)
            device = UserDevice.objects.get(user=request.user, ip_address=ip_address, is_active=True)
            device.save()  # Обновит last_activity благодаря auto_now=True
        except UserDevice.DoesNotExist:
            pass  # Устройство будет создано при следующем входе
    
    def _get_client_ip(self, request):
        """Получает IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class ProtectedView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Защищенное представление. Проверяет валидность токена. Возвращает пустой ответ при успешной авторизации. Полные данные загружаются через /profile/.",
        responses={
            200: openapi.Response(
                description="Токен валиден, пользователь авторизован.",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={}
                )
            ),
            401: "Неавторизованный доступ."
        },
        security=[{'Bearer': []}]
    )
    def get(self, request):
        # Обновляем последнюю активность текущего устройства
        self._update_device_activity(request)
        
        # Создаем профиль если его нет
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        # Возвращаем пустой ответ - успешный статус 200 означает валидный токен
        # Все данные пользователя загружаются через /profile/
        return Response({}, status=status.HTTP_200_OK)
    
    def _update_device_activity(self, request):
        """Обновляет последнюю активность устройства пользователя"""
        try:
            ip_address = self._get_client_ip(request)
            device = UserDevice.objects.get(user=request.user, ip_address=ip_address, is_active=True)
            device.save()  # Обновит last_activity благодаря auto_now=True
        except UserDevice.DoesNotExist:
            # Если устройство не найдено, создаем его
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            device_type = self._detect_device_type(user_agent)
            device_name = self._get_device_name(user_agent, device_type)
            
            UserDevice.objects.create(
                user=request.user,
                ip_address=ip_address,
                device_type=device_type,
                device_name=device_name,
                user_agent=user_agent,
                city='Неизвестно',
                country='Неизвестно',
                is_active=True,
            )
    
    def _get_client_ip(self, request):
        """Получает IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _detect_device_type(self, user_agent):
        """Определяет тип устройства по User-Agent"""
        user_agent = user_agent.lower()
        
        if 'mobile' in user_agent or 'android' in user_agent or 'iphone' in user_agent:
            return 'mobile'
        elif 'tablet' in user_agent or 'ipad' in user_agent:
            return 'tablet'
        elif 'macintosh' in user_agent or 'mac os' in user_agent:
            return 'laptop'
        elif 'windows' in user_agent or 'linux' in user_agent:
            return 'desktop'
        else:
            return 'desktop'  # По умолчанию
    
    def _get_device_name(self, user_agent, device_type):
        """Получает название устройства по User-Agent"""
        user_agent = user_agent.lower()
        
        if 'windows' in user_agent:
            return 'Windows PC'
        elif 'macintosh' in user_agent or 'mac os' in user_agent:
            return 'Mac'
        elif 'linux' in user_agent:
            return 'Linux PC'
        elif 'android' in user_agent:
            return 'Android Device'
        elif 'iphone' in user_agent:
            return 'iPhone'
        elif 'ipad' in user_agent:
            return 'iPad'
        else:
            device_names = {
                'mobile': 'Mobile Device',
                'tablet': 'Tablet',
                'laptop': 'Laptop',
                'desktop': 'Desktop'
            }
            return device_names.get(device_type, 'Unknown Device')

class ChangePasswordView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Смена пароля пользователя.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'current_password': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_PASSWORD,
                    description='Текущий пароль'
                ),
                'new_password': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_PASSWORD,
                    description='Новый пароль'
                ),
                'confirm_password': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_PASSWORD,
                    description='Подтверждение нового пароля'
                ),
            },
            required=['current_password', 'new_password', 'confirm_password'],
        ),
        responses={
            200: "Пароль успешно изменён.",
            400: "Ошибка валидации данных."
        },
        security=[{'Bearer': []}]
    )
    def post(self, request):
        # Обновляем активность устройства
        self._update_device_activity(request)
        
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            return Response(
                {"message": "Пароль успешно изменён."}, 
                status=status.HTTP_200_OK
            )
        
        errors = parse_errors_to_dict(serializer.errors)
        return Response(
            errors, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def _update_device_activity(self, request):
        """Обновляет последнюю активность устройства пользователя"""
        try:
            ip_address = self._get_client_ip(request)
            device = UserDevice.objects.get(user=request.user, ip_address=ip_address, is_active=True)
            device.save()  # Обновит last_activity благодаря auto_now=True
        except UserDevice.DoesNotExist:
            pass  # Устройство будет создано при следующем входе
    
    def _get_client_ip(self, request):
        """Получает IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class UserDevicesView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение списка устройств пользователя.",
        responses={
            200: openapi.Response(
                description="Список устройств пользователя.",
                schema=UserDeviceSerializer(many=True)
            ),
        },
        security=[{'Bearer': []}]
    )
    def get(self, request):
        # Обновляем активность устройства
        self._update_device_activity(request)
        
        devices = UserDevice.objects.filter(user=request.user).order_by('-last_activity')
        serializer = UserDeviceSerializer(devices, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def _update_device_activity(self, request):
        """Обновляет последнюю активность устройства пользователя"""
        try:
            ip_address = self._get_client_ip(request)
            device = UserDevice.objects.get(user=request.user, ip_address=ip_address, is_active=True)
            device.save()  # Обновит last_activity благодаря auto_now=True
        except UserDevice.DoesNotExist:
            pass  # Устройство будет создано при следующем входе
    
    def _get_client_ip(self, request):
        """Получает IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class UserDeviceDetailView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Удаление устройства пользователя (завершение сессии).",
        responses={
            200: "Устройство успешно удалено.",
            404: "Устройство не найдено."
        },
        security=[{'Bearer': []}]
    )
    def delete(self, request, device_id):
        try:
            device = UserDevice.objects.get(id=device_id, user=request.user)
            device.delete()
            return Response(
                {"message": "Устройство успешно удалено."}, 
                status=status.HTTP_200_OK
            )
        except UserDevice.DoesNotExist:
            return Response(
                {"error": "Устройство не найдено."}, 
                status=status.HTTP_404_NOT_FOUND
            )

class UserProfileView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение профиля текущего пользователя.",
        responses={
            200: openapi.Response(
                description="Данные профиля пользователя.",
                schema=CMSUserSerializer()
            ),
        },
        security=[{'Bearer': []}]
    )
    def get(self, request):
        # Создаем профиль если его нет
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        serializer = CMSUserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @swagger_auto_schema(
        operation_description="Обновление профиля пользователя.",
        request_body=UpdateUserProfileSerializer,
        responses={
            200: "Профиль успешно обновлен.",
            400: "Ошибка валидации данных."
        },
        security=[{'Bearer': []}]
    )
    def put(self, request):
        # Создаем профиль если его нет
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        serializer = UpdateUserProfileSerializer(profile, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()

            user = User.objects.select_related('adp_profile').get(pk=request.user.pk)
            user_serializer = CMSUserSerializer(user)
            return Response(user_serializer.data, status=status.HTTP_200_OK)
        
        errors = parse_errors_to_dict(serializer.errors)
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

class UserSecuritySettingsView(BaseAPIViewAuthMixin):
    @swagger_auto_schema(
        operation_description="Получение настроек безопасности пользователя.",
        responses={
            200: openapi.Response(
                description="Настройки безопасности.",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'two_factor_enabled': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'email_notifications': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'push_notifications': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'sms_notifications': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'profile_visibility': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
        },
        security=[{'Bearer': []}]
    )
    def get(self, request):
        # Создаем профиль если его нет
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        security_data = {
            'two_factor_enabled': profile.two_factor_enabled,
            'email_notifications': profile.email_notifications,
            'push_notifications': profile.push_notifications,
            'sms_notifications': profile.sms_notifications,
            'profile_visibility': profile.profile_visibility,
        }
        
        return Response(security_data, status=status.HTTP_200_OK)
    
    @swagger_auto_schema(
        operation_description=(
            "Обновление настроек безопасности. "
            "Поле email_notifications устарело: управление каналами уведомлений — "
            "через PATCH /notifications/preferences/ (панель «Уведомления»)."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'two_factor_enabled': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'push_notifications': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'sms_notifications': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'profile_visibility': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={
            200: "Настройки безопасности обновлены.",
            400: "Ошибка валидации данных."
        },
        security=[{'Bearer': []}]
    )
    def put(self, request):
        # Создаем профиль если его нет
        profile, created = UserProfile.objects.get_or_create(user=request.user)

        # email_notifications исключён: источник истины — NotificationPreference
        # (sentinel-строка '*'/'*'), редактируется через панель «Уведомления».
        for field in ['two_factor_enabled', 'push_notifications',
                      'sms_notifications', 'profile_visibility']:
            if field in request.data:
                setattr(profile, field, request.data[field])

        profile.save()

        return Response({"message": "Настройки безопасности обновлены."}, status=status.HTTP_200_OK)


class ImportUsersView(BaseAPIViewAuthMixin):
    """
    Импорт пользователей из Excel или CSV файла через Celery с real-time прогрессом.
    Ожидаемые столбцы: Фамилия, Имя, Отчество, Логин, E-mail.
    Пароль по умолчанию: "1".
    Проверка дубликатов по ФИО.
    """
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_description="Импорт пользователей из Excel (.xlsx, .xls) или CSV файла через Celery.",
        manual_parameters=[
            openapi.Parameter(
                'file',
                openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                description='Файл Excel или CSV с пользователями'
            ),
            openapi.Parameter(
                'skip_welcome_emails',
                openapi.IN_FORM,
                type=openapi.TYPE_BOOLEAN,
                description='Не отправлять приветственные письма пользователям (по умолчанию: false)'
            )
        ],
        responses={
            200: openapi.Response(
                description="Task ID для отслеживания прогресса.",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'task_id': openapi.Schema(type=openapi.TYPE_STRING),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
            400: "Ошибка валидации."
        },
        security=[{'Bearer': []}]
    )
    def post(self, request):
        from src.core.cms.adp.tasks import import_users_task
        
        # Проверяем флаг отключения приветственных писем
        skip_welcome_emails = request.POST.get('skip_welcome_emails', 'false').lower() in ('true', '1', 'yes')
        
        logger.warning(f'Запуск импорта пользователей через Celery. Пользователь: {request.user.username} (ID: {request.user.id}), skip_welcome_emails: {skip_welcome_emails}')
        
        if 'file' not in request.FILES:
            logger.warning('Попытка импорта без файла')
            return Response(
                {'error': 'Файл не найден'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file = request.FILES['file']
        file_name = file.name.lower()
        
        logger.warning(f'Получен файл для импорта: {file.name}, размер: {file.size} байт')
        
        # Проверяем тип файла
        if not file_name.endswith(('.xlsx', '.xls', '.csv')):
            logger.warning(f'Неподдерживаемый формат файла: {file.name}')
            return Response(
                {'error': 'Поддерживаются только файлы Excel (.xlsx, .xls) и CSV (.csv)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Читаем содержимое файла в память
            file_content = file.read()
            
            # Запускаем Celery задачу
            task = import_users_task.delay(
                file_content=file_content,
                file_name=file.name,
                skip_welcome_emails=skip_welcome_emails
            )
            
            logger.warning(f'Celery задача запущена: task_id={task.id}')
            
            return Response({
                'task_id': task.id,
                'message': 'Импорт запущен. Используйте task_id для отслеживания прогресса.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f'Ошибка при запуске задачи: {str(e)}', exc_info=True)
            return Response({
                'error': f'Ошибка при запуске импорта: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)


class ImportUsersTaskStatusView(BaseAPIViewAuthMixin):
    """
    Получение статуса Celery задачи импорта пользователей
    """
    
    @swagger_auto_schema(
        operation_description="Получить статус задачи импорта пользователей",
        manual_parameters=[
            openapi.Parameter(
                'task_id',
                openapi.IN_PATH,
                type=openapi.TYPE_STRING,
                description='ID Celery задачи'
            )
        ],
        responses={
            200: openapi.Response(
                description="Статус задачи",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'state': openapi.Schema(type=openapi.TYPE_STRING),
                        'current': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'total': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'created': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'skipped': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'progress': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'result': openapi.Schema(type=openapi.TYPE_OBJECT),
                    }
                )
            )
        },
        security=[{'Bearer': []}]
    )
    def get(self, request, task_id):
        from celery.result import AsyncResult
        
        task = AsyncResult(task_id)
        
        # Получаем индекс последнего лога для накопления
        last_log_index = int(request.query_params.get('last_log_index', 0))
        
        if task.state == 'PENDING':
            response = {
                'state': task.state,
                'current': 0,
                'total': 0,
                'created': 0,
                'skipped': 0,
                'progress': 0,
                'new_logs': [],
                'status': 'Задача в очереди...'
            }
        elif task.state == 'PROGRESS':
            all_logs = task.info.get('logs', [])
            logs_total = task.info.get('logs_total', len(all_logs))
            # Логи в meta — только последние N; считаем срез для клиента по last_log_index
            start = last_log_index - (logs_total - len(all_logs))
            if start >= len(all_logs):
                new_logs = []
            else:
                new_logs = all_logs[max(0, start):]
            if not new_logs and task.info.get('last_log') and last_log_index < logs_total:
                new_logs = [task.info.get('last_log')]
            response = {
                'state': task.state,
                'current': task.info.get('current', 0),
                'total': task.info.get('total', 0),
                'created': task.info.get('created', 0),
                'skipped': task.info.get('skipped', 0),
                'progress': task.info.get('progress', 0),
                'new_logs': new_logs,
                'logs_total': logs_total,
                'status': 'Обработка...'
            }
        elif task.state == 'SUCCESS':
            result = task.result
            response = {
                'state': task.state,
                'current': result.get('total', 0),
                'total': result.get('total', 0),
                'created': result.get('created', 0),
                'skipped': result.get('skipped', 0),
                'progress': 100,
                'status': 'Завершено',
                'result': result
            }
        elif task.state == 'FAILURE':
            response = {
                'state': task.state,
                'current': 0,
                'total': 0,
                'created': 0,
                'skipped': 0,
                'progress': 0,
                'status': 'Ошибка',
                'error': str(task.info)
            }
        else:
            response = {
                'state': task.state,
                'current': 0,
                'total': 0,
                'created': 0,
                'skipped': 0,
                'progress': 0,
                'new_logs': [],
                'status': str(task.state)
            }
        
        return Response(response, status=status.HTTP_200_OK)