"""Versioned operation metadata and lazy execution on prepared tables."""
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import re
from threading import RLock
from typing import Callable


class OperationError(ValueError):
    """Invalid operation or parameters; safe to report as an input error."""


def validate_parameters(schema, values):
    if not isinstance(values, dict):
        raise OperationError('parameters must be an object')
    try:
        json.dumps(values, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OperationError('parameters must contain finite JSON values') from exc
    properties = schema['properties']
    if set(values) - properties.keys():
        raise OperationError('unknown parameters: ' + ', '.join(sorted(set(values) - properties.keys())))
    result = deepcopy(values)
    for name, spec in properties.items():
        if name not in result and 'default' in spec:
            result[name] = deepcopy(spec['default'])
        if name not in result:
            if name in schema.get('required', []):
                raise OperationError('missing parameter: ' + name)
            continue
        value, kind = result[name], spec['type']
        if kind == 'string':
            valid = isinstance(value, str) and bool(value.strip())
        elif kind == 'integer':
            valid = type(value) is int and spec.get('minimum', -math.inf) <= value <= spec.get('maximum', math.inf)
        elif kind == 'array':
            valid = (isinstance(value, list) and len(value) >= spec.get('minItems', 0)
                     and all(isinstance(item, str) and bool(item.strip()) for item in value)
                     and len(value) == len(set(value)))
        else:
            raise OperationError('unsupported parameter schema: ' + kind)
        if not valid:
            raise OperationError('invalid parameter: ' + name)
    return result


@dataclass(frozen=True)
class Operation:
    id: str
    title: str
    category: str
    result_kind: str
    parameters_schema: dict
    output_schema: dict
    version: int = 1
    memory_mb: int = 2048
    cpu: float = 1
    gpu: bool = False
    python_groups: tuple = ('analytics',)
    tools: tuple = ()
    models: tuple = ()

    def descriptor(self):
        return deepcopy({
            'id': self.id, 'version': self.version, 'title': self.title,
            'category': self.category, 'result_kind': self.result_kind,
            'input_schema': {'type': 'object', 'required': ['kind', 'public_id'],
                             'properties': {'kind': {'type': 'string'}, 'public_id': {'type': 'string', 'format': 'uuid'}},
                             'additionalProperties': False},
            'parameters_schema': self.parameters_schema, 'output_schema': self.output_schema,
            'dependencies': {'python_groups': list(self.python_groups), 'tools': list(self.tools), 'models': list(self.models)},
            'resources': {'cpu': self.cpu, 'memory_mb': self.memory_mb, 'gpu': self.gpu},
        })


class OperationRegistry:
    def __init__(self):
        self._entries = {}
        self._lock = RLock()

    def register(self, operation: Operation, executor: Callable):
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{0,79}', operation.id) or operation.version < 1:
            raise OperationError('invalid operation identity')
        if not callable(executor):
            raise OperationError('executor must be callable')
        if type(operation.memory_mb) is not int or operation.memory_mb <= 0 or type(operation.gpu) is not bool:
            raise OperationError('invalid resources')
        if isinstance(operation.cpu, bool) or not isinstance(operation.cpu, (int, float)) or not math.isfinite(operation.cpu) or operation.cpu <= 0:
            raise OperationError('invalid cpu requirement')
        json.dumps(operation.descriptor(), allow_nan=False)
        with self._lock:
            if operation.id in self._entries:
                raise OperationError('duplicate operation: ' + operation.id)
            self._entries[operation.id] = (deepcopy(operation), executor)

    def get(self, operation_id):
        try:
            with self._lock:
                return deepcopy(self._entries[operation_id][0])
        except (KeyError, TypeError) as exc:
            raise OperationError('unknown operation') from exc

    def catalog(self):
        with self._lock:
            return [entry[0].descriptor() for _, entry in sorted(self._entries.items())]

    def validate(self, operation_id, parameters):
        return validate_parameters(self.get(operation_id).parameters_schema, parameters)

    def execute(self, operation_id, frame, parameters, progress_cb=None):
        config = self.validate(operation_id, parameters)
        with self._lock:
            operation, executor = self._entries[operation_id]
        for name, spec in operation.parameters_schema['properties'].items():
            if not spec.get('x-column-role') or name not in config:
                continue
            columns = config[name] if isinstance(config[name], list) else [config[name]]
            if any(column not in frame.columns for column in columns):
                raise OperationError('unknown table column: ' + name)
        if operation_id == 'linear' and config['target_field'] in config['feature_fields']:
            raise OperationError('target must not be a feature')
        result = executor(frame, config, progress_cb)
        if not isinstance(result, dict) or not set(operation.output_schema['required']) <= result.keys():
            raise OperationError('invalid operation output')
        json.dumps(result, allow_nan=False)
        return result


def create_registry():
    from .operation_builtins import register_builtins
    registry = OperationRegistry()
    register_builtins(registry)
    return registry


# Creating descriptors does not import numerical or machine-learning libraries.
registry = create_registry()
