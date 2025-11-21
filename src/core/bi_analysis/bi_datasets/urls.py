from django.urls import path, include

from src.core.bi_analysis.bi_datasets.views import DataSetFieldViewSet, DatasetParamViewSet
from src.core.bi_analysis.bi_datasets.views import (
DatasetDetailView, DatasetPreviewView, DatasetPreviewTaskStatusView,
    DataSetTableViewSet, DataSetFieldViewSet,
    TempUploadView, FileUploadDetailView,
    FinalizeUploadView, XlsxSheetListView,
    XlsxTempPreviewView, FilePreviewTaskStatusView, FileUploadByConnectionView, AddTableToDatasetView, DatasetRemoveRelationView, DatasetColumnsAPIView,
    RenameDatasetColumnsView, DatasetListCreateView, DatasetJoinTableView, DataSetTableColumnsView, DatasetDraftPreviewView, DatasetAddRelationView, DatasetRowsAPIView, DatasetRowsAggAPIView, DatasetFieldValuesView
)

from rest_framework.routers import SimpleRouter

router = SimpleRouter()
router.register(r'tables', DataSetTableViewSet, basename='dataset-tables')
router.register(r'fields', DataSetFieldViewSet, basename='dataset-fields')
router.register(r'params', DatasetParamViewSet, basename='dataset-params')

urlpatterns = [
    path('upload/', TempUploadView.as_view(), name='temp-upload'),
    path('upload/<int:pk>/', FileUploadDetailView.as_view(), name='file-upload-detail'),
    path('upload/finalize/', FinalizeUploadView.as_view(), name='finalize-upload'),
    path('xlsx/sheets/', XlsxSheetListView.as_view(), name='xlsx-sheet-list'),
    path('xlsx/preview/', XlsxTempPreviewView.as_view(), name='xlsx-preview'),
    path('xlsx/preview/task-status/', FilePreviewTaskStatusView.as_view(), name='xlsx-preview-task-status'),
    path('connection/<int:connection_id>/files/', FileUploadByConnectionView.as_view(), name='fileupload-by-connection'),
    path('<int:pk>/auto-join/', DatasetJoinTableView.as_view(), name="bi_datasets-auto-join"),
    path('<int:pk>/add-table/', AddTableToDatasetView.as_view(), name="add_table_to_dataset"),
    path('tables/<int:pk>/columns/', DataSetTableColumnsView.as_view(), name='dataset-table-columns'),
    path('draft_preview/', DatasetDraftPreviewView.as_view(), name='bi_datasets-draft-preview'),
    path('<int:dataset_id>/add-relation/', DatasetAddRelationView.as_view()),
    path('<int:pk>/rows/', DatasetRowsAPIView.as_view(), name='dataset-rows'),
    path('<int:pk>/rows-agg/', DatasetRowsAggAPIView.as_view(), name='dataset-rows-agg'),
    path('<int:pk>/columns/', DatasetColumnsAPIView.as_view(), name='dataset-columns'),
    path('<int:pk>/field-values/<int:field_id>/', DatasetFieldValuesView.as_view(), name='dataset-field-values'),

    path('', DatasetListCreateView.as_view(), name='bi_datasets-list-create'),
    path('<int:pk>/', DatasetDetailView.as_view(), name='bi_datasets-detail'),
    path('<int:pk>/preview/', DatasetPreviewView.as_view(), name='bi_datasets-preview'),
    path('preview/task-status/', DatasetPreviewTaskStatusView.as_view(), name='bi_datasets-preview-task-status'),
    path('<int:pk>/rename_columns/', RenameDatasetColumnsView.as_view(), name='bi_datasets-rename-columns'),
    path('<int:pk>/remove-relation/', DatasetRemoveRelationView.as_view(), name='dataset-remove-relation'),

    path('', include(router.urls)),
]