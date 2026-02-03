from rest_framework import serializers
from src.core.bi_analysis.bi_dashboards.models import Dashboard, DashboardPage, DashboardItem
from src.core.bi_analysis.bi_charts.models import Chart


class DashboardItemSerializer(serializers.ModelSerializer):
    """Сериализатор для элемента дашборда."""
    
    class Meta:
        model = DashboardItem
        fields = [
            'id', 'type', 'x', 'y', 'width', 'height', 'config', 'order'
        ]


class DashboardPageSerializer(serializers.ModelSerializer):
    """Сериализатор для страницы дашборда с элементами."""
    items = DashboardItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = DashboardPage
        fields = ['id', 'name', 'order', 'items']


class DashboardPageWriteSerializer(serializers.ModelSerializer):
    """Сериализатор для записи страницы дашборда с элементами."""
    items = DashboardItemSerializer(many=True, required=False)
    
    class Meta:
        model = DashboardPage
        fields = ['id', 'name', 'order', 'items']
    
    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        page = DashboardPage.objects.create(**validated_data)
        
        for idx, item_data in enumerate(items_data):
            # Создаем копию item_data и удаляем order, так как устанавливаем его через индекс
            item_data_copy = {k: v for k, v in item_data.items() if k != 'order'}
            DashboardItem.objects.create(
                page=page,
                order=idx,
                **item_data_copy
            )
        
        return page
    
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        
        instance.name = validated_data.get('name', instance.name)
        instance.order = validated_data.get('order', instance.order)
        instance.save()
        
        if items_data is not None:
            # Удаляем старые элементы
            instance.items.all().delete()
            # Создаем новые элементы
            for idx, item_data in enumerate(items_data):
                # Создаем копию item_data и удаляем order, так как устанавливаем его через индекс
                item_data_copy = {k: v for k, v in item_data.items() if k != 'order'}
                DashboardItem.objects.create(
                    page=instance,
                    order=idx,
                    **item_data_copy
                )
        
        return instance


class DashboardSerializer(serializers.ModelSerializer):
    """Сериализатор для дашборда со страницами."""
    pages = DashboardPageSerializer(many=True, read_only=True)
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)
    charts_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Dashboard
        fields = [
            'id', 'name', 'description', 'owner', 'owner_id', 'owner_username',
            'created_at', 'updated_at', 'pages', 'charts_count'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at', 'charts_count']


class DashboardWriteSerializer(serializers.ModelSerializer):
    """Сериализатор для записи дашборда со страницами."""
    pages = DashboardPageWriteSerializer(many=True, required=False)
    
    class Meta:
        model = Dashboard
        fields = ['id', 'name', 'description', 'pages']
        read_only_fields = ['id']
    
    def create(self, validated_data):
        pages_data = validated_data.pop('pages', [])
        dashboard = Dashboard.objects.create(**validated_data)
        
        for idx, page_data in enumerate(pages_data):
            items_data = page_data.pop('items', [])
            # Удаляем order из page_data, так как устанавливаем его через индекс
            page_data.pop('order', None)
            page = DashboardPage.objects.create(
                dashboard=dashboard,
                order=idx,
                **page_data
            )
            
            for item_idx, item_data in enumerate(items_data):
                # Создаем копию item_data и удаляем order, так как устанавливаем его через индекс
                item_data_copy = {k: v for k, v in item_data.items() if k != 'order'}
                DashboardItem.objects.create(
                    page=page,
                    order=item_idx,
                    **item_data_copy
                )
        
        return dashboard
    
    def update(self, instance, validated_data):
        pages_data = validated_data.pop('pages', None)
        
        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.save()
        
        if pages_data is not None:
            # Удаляем старые страницы (и их элементы)
            instance.pages.all().delete()
            # Создаем новые страницы
            for idx, page_data in enumerate(pages_data):
                items_data = page_data.pop('items', [])
                # Удаляем order из page_data, так как устанавливаем его через индекс
                page_data.pop('order', None)
                page = DashboardPage.objects.create(
                    dashboard=instance,
                    order=idx,
                    **page_data
                )
                
                for item_idx, item_data in enumerate(items_data):
                    # Создаем копию item_data и удаляем order, так как устанавливаем его через индекс
                    item_data_copy = {k: v for k, v in item_data.items() if k != 'order'}
                    DashboardItem.objects.create(
                        page=page,
                        order=item_idx,
                        **item_data_copy
                    )
        
        return instance


class DashboardShortSerializer(serializers.ModelSerializer):
    """Короткий сериализатор для списка дашбордов."""
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)
    charts_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Dashboard
        fields = [
            'id', 'name', 'description', 'owner_id', 'owner_username',
            'created_at', 'updated_at', 'charts_count'
        ]


