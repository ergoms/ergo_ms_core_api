"""Built-in descriptors; numerical dependencies load only inside an executor."""
from .operations import Operation


def column(title, role='numeric'):
    return {'type': 'string', 'title': title, 'x-column-role': role}


def integer(title, default, minimum=0, maximum=10):
    return {'type': 'integer', 'title': title, 'default': default, 'minimum': minimum, 'maximum': maximum}


def schema(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


def eda(frame, config, progress_cb):
    from .eda import compute_summary, compute_distributions, compute_correlations, compute_outliers
    result = {}
    for progress, key, title, function in (
        (0.05, 'summary', 'Вычисление сводки по колонкам', compute_summary),
        (0.30, 'distributions', 'Вычисление распределений', compute_distributions),
        (0.55, 'correlations', 'Вычисление корреляций', compute_correlations),
        (0.80, 'outliers', 'Поиск выбросов', compute_outliers),
    ):
        if progress_cb:
            progress_cb(progress, title)
        result[key] = function(frame)
    if progress_cb:
        progress_cb(0.95, 'Формирование результата')
    result['meta'] = {'total_rows': len(frame), 'total_columns': len(frame.columns)}
    return result


def modeling(kind):
    def execute(frame, config, progress_cb):
        from . import modeling as engines
        return getattr(engines, 'run_' + kind)(frame, config, progress_cb)
    return execute


def register_builtins(registry):
    registry.register(Operation('eda', 'Разведочный анализ (EDA)', 'statistics', 'eda', schema({}),
        {'type': 'object', 'required': ['summary', 'distributions', 'correlations', 'outliers', 'meta']}), eda)
    registry.register(Operation('linear', 'Линейная регрессия', 'modeling', 'regression', schema({
        'target_field': column('Целевая переменная'),
        'feature_fields': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1,
                          'uniqueItems': True, 'title': 'Признаки', 'x-column-role': 'numeric'},
    }, ('target_field', 'feature_fields')), {'type': 'object', 'required': ['meta', 'metrics']}), modeling('linear_regression'))
    timeseries = {'value_field': column('Значение'), 'date_field': column('Дата', 'date'),
                  'p': integer('p', 1), 'd': integer('d', 1), 'q': integer('q', 1),
                  'forecast_steps': integer('Шагов прогноза', 10, 1, 1000)}
    seasonal = {**timeseries, 'P': integer('P', 1, 0, 5), 'D': integer('D', 1, 0, 5),
                'Q': integer('Q', 1, 0, 5), 'm': integer('Период сезона', 12, 2, 365)}
    for kind, properties in [('arima', timeseries), ('sarima', seasonal)]:
        registry.register(Operation(kind, kind.upper(), 'forecast', 'forecast',
            schema(properties, ('value_field', 'date_field')),
            {'type': 'object', 'required': ['meta', 'forecast']}), modeling(kind))
    registry.register(Operation('boxplot', 'Диаграмма ящик с усами', 'statistics', 'boxplot', schema({
        'fields': {'type': 'array', 'items': {'type': 'string'}, 'uniqueItems': True,
                   'default': [], 'title': 'Поля (пусто — все числовые)', 'x-column-role': 'numeric'},
    }), {'type': 'object', 'required': ['meta', 'boxplots']}), modeling('boxplot'))
