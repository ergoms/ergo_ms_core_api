import json
import subprocess
import sys
import unittest

import polars as pl

from src.core.analytics.operations import Operation, OperationError, OperationRegistry, registry
from src.core.analytics import eda, modeling


class OperationTests(unittest.TestCase):
    def test_catalog_is_versioned_json_and_copies_cannot_mutate_registry(self):
        catalog = registry.catalog()
        self.assertEqual({item['id'] for item in catalog}, {'eda', 'linear', 'arima', 'sarima', 'boxplot'})
        for item in catalog:
            self.assertEqual(item['version'], 1)
            self.assertFalse(item['resources']['gpu'])
            self.assertEqual(item['dependencies']['python_groups'], ['analytics'])
            json.dumps(item, allow_nan=False)
        catalog[0]['parameters_schema']['properties'].clear()
        self.assertTrue(registry.get('arima').parameters_schema['properties'])

    def test_catalog_import_does_not_import_numerical_dependencies(self):
        code = ('import sys; from src.core.analytics.operations import registry; registry.catalog(); '
                'assert not any(name in sys.modules for name in ("polars","numpy","torch","django"))')
        subprocess.run([sys.executable, '-c', code], check=True, capture_output=True)

    def test_invalid_parameters_are_rejected_before_execution(self):
        for operation, parameters in [('missing', {}), ('eda', {'unknown': 1}), ('boxplot', []),
                                     ('arima', {'value_field': 'x'}), ('linear', {'target_field': 'x', 'feature_fields': []}),
                                     ('arima', {'value_field': 'x', 'date_field': 'day', 'p': True}),
                                     ('arima', {'value_field': 'x', 'date_field': 'day', 'forecast_steps': 1000000})]:
            with self.subTest(operation=operation, parameters=parameters), self.assertRaises(OperationError):
                registry.validate(operation, parameters)

    def test_defaults_are_normalized_and_input_is_unchanged(self):
        supplied = {'value_field': 'x', 'date_field': 'day'}
        result = registry.validate('arima', supplied)
        self.assertEqual((result['p'], result['d'], result['q'], result['forecast_steps']), (1, 1, 1, 10))
        self.assertEqual(supplied, {'value_field': 'x', 'date_field': 'day'})

    def test_eda_composes_the_existing_functions_exactly(self):
        frame = pl.DataFrame({'x': [1, 2, None, 100], 'text': ['a', 'b', '', None]})
        progress = []
        result = registry.execute('eda', frame, {}, lambda value, title: progress.append(value))
        self.assertEqual(result['summary'], eda.compute_summary(frame))
        self.assertEqual(result['distributions']['numeric'], eda.compute_distributions(frame)['numeric'])
        self.assertEqual(result['correlations'], eda.compute_correlations(frame))
        self.assertEqual(result['outliers'], eda.compute_outliers(frame))
        self.assertEqual(progress, [0.05, 0.3, 0.55, 0.8, 0.95])

    def test_boxplot_matches_previous_entry_point(self):
        frame = pl.DataFrame({'x': [1, 2, 3, 100, None]})
        self.assertEqual(registry.execute('boxplot', frame, {'fields': ['x']}), modeling.run_boxplot(frame, {'fields': ['x']}))

    def test_duplicate_columns_unknown_columns_and_target_as_feature_are_rejected(self):
        for config in ({'target_field': 'x', 'feature_fields': ['x']},
                       {'target_field': 'x', 'feature_fields': ['y', 'y']},
                       {'target_field': 'absent', 'feature_fields': ['y']}):
            with self.assertRaises(OperationError):
                registry.execute('linear', pl.DataFrame({'x': [1], 'y': [2]}), config)

    def test_extensions_reject_duplicate_ids_and_invalid_outputs(self):
        custom = OperationRegistry()
        operation = Operation('extension', 'Extension', 'table', 'table',
                              {'properties': {}, 'required': []}, {'required': ['rows']})
        custom.register(operation, lambda frame, config, cb: {})
        with self.assertRaises(OperationError):
            custom.register(operation, lambda *args: {})
        with self.assertRaises(OperationError):
            custom.execute('extension', pl.DataFrame(), {})

    def test_extension_dependencies_and_resources_are_serializable_and_independent(self):
        operation = Operation('external', 'External', 'table', 'table', {'properties': {}, 'required': []},
                              {'required': ['rows']}, cpu=2, gpu=True, python_groups=('analytics', 'extra'),
                              tools=('tool-id',), models=({'provider': 'local', 'id': 'model-id'},))
        custom = OperationRegistry(); custom.register(operation, lambda frame, config, cb: {'rows': []})
        descriptor = custom.catalog()[0]
        self.assertEqual(descriptor['resources']['cpu'], 2)
        self.assertEqual(descriptor['dependencies']['models'][0]['id'], 'model-id')
        descriptor['dependencies']['models'][0]['id'] = 'changed'
        self.assertEqual(custom.catalog()[0]['dependencies']['models'][0]['id'], 'model-id')
