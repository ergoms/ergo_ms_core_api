import time

from django.shortcuts import render

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from drf_yasg.utils import swagger_auto_schema

from src.core.bi_analysis.models import ReportExecutionLog, ReportResult
from src.core.bi_analysis.serializers import ReportRunSerializer
from src.core.bi_analysis.services.query_executor import run_pg_query, run_clickhouse_query, run_mssql_query

# Создавайте свои представления здесь
class RunReportAPIView(APIView):
    
    @swagger_auto_schema(
        request_body=ReportRunSerializer,
        operation_summary="Запуск BI-отчёта по report_id",
        operation_description=(
            "Выполняет SQL-запрос, связанный с выбранным отчётом (`ReportConfig`).\n\n"
            "Что делает:\n"
            "- Определяет источник данных (PostgreSQL, MS SQL, ClickHouse)\n"
            "- Выполняет SQL-запрос, указанный в отчёте\n"
            "- Логирует выполнение в `ReportExecutionLog`\n"
            "- Сохраняет результат в `ReportResult`\n"
            "- Возвращает результат пользователю\n\n"
        )
    )
    def post(self, request):
        serializer = ReportRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report = serializer.validated_data['report_id']
        query = report.query
        source_type = report.source_type

        # Выбор нужного движка
        executor_map = {
            'postgres': run_pg_query,
            'clickhouse': run_clickhouse_query,
            'mssql': run_mssql_query,
        }

        run_fn = executor_map.get(source_type)
        if not run_fn:
            return Response({'error': 'Неподдерживаемый тип базы данных.'}, status=400)

        start_time = time.time()
        try:
            result = run_fn(query)
            duration = int((time.time() - start_time) * 1000)

            log = ReportExecutionLog.objects.create(
                report=report,
                status='success',
                duration_ms=duration,
            )

            saved = ReportResult.objects.create(
                report=report,
                execution=log,
                result_data=result,
                row_count=len(result)
            )

            return Response({
                'status': 'ok',
                'rows': saved.row_count,
                'result': saved.result_data,
                'log_id': log.id
            })

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            log = ReportExecutionLog.objects.create(
                report=report,
                status='error',
                duration_ms=duration,
                error_message=str(e)
            )
            return Response({'error': str(e)}, status=500)