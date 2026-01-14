"""
Подмодуль управления меню.
Содержит модели, сериализаторы, views и сервисы для работы с боковым меню.
"""

from .models import MenuItem, MenuSeparator, MenuAccessLog
from .serializers import (
    MenuItemSerializer, MenuItemTreeSerializer, MenuSeparatorSerializer,
    MenuItemCreateSerializer, MenuItemUpdateSerializer, 
    MenuItemReorderSerializer, MenuAccessLogSerializer
)
from .views import (
    UserMenuView, MenuItemListView, MenuItemDetailView,
    MenuItemReorderView, MenuSeparatorListView, MenuSeparatorDetailView,
    MenuAccessLogView, AvailableIconsView
)

__all__ = [
    # Models
    'MenuItem', 'MenuSeparator', 'MenuAccessLog',
    # Serializers
    'MenuItemSerializer', 'MenuItemTreeSerializer', 'MenuSeparatorSerializer',
    'MenuItemCreateSerializer', 'MenuItemUpdateSerializer', 
    'MenuItemReorderSerializer', 'MenuAccessLogSerializer',
    # Views
    'UserMenuView', 'MenuItemListView', 'MenuItemDetailView',
    'MenuItemReorderView', 'MenuSeparatorListView', 'MenuSeparatorDetailView',
    'MenuAccessLogView', 'AvailableIconsView'
]

