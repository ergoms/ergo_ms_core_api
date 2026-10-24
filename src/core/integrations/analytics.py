"""JSON-only operation dispatch; storage, authorization and scheduling belong to providers."""
import json

from src.core.analytics.operations import OperationError, registry
from . import bridge
from .module_contracts import (
    ANALYTICS_BACKENDS, ANALYTICS_LIST_OPERATIONS, ANALYTICS_RUN_OPERATION, ANALYTICS_GET_STATUS,
)


def _backend(provider):
    backend = bridge.all(ANALYTICS_BACKENDS).get(provider)
    if not isinstance(backend, dict) or not all(isinstance(backend.get(key), str) for key in ('catalog', 'run', 'status')):
        raise OperationError('unknown analytics provider')
    return backend


@bridge.provide_op(ANALYTICS_LIST_OPERATIONS)
def list_operations(*, provider=None, **_):
    if provider is None:
        return registry.catalog()
    return bridge.call(_backend(provider)['catalog'])


@bridge.provide_op(ANALYTICS_RUN_OPERATION)
def run_operation(*, provider, operation_id, input_ref, parameters, user=None, user_public_id=None, **_):
    json.dumps({'input_ref': input_ref, 'parameters': parameters}, allow_nan=False)
    return bridge.call(_backend(provider)['run'], operation_id=operation_id, input_ref=input_ref,
                       parameters=parameters, user=user, user_public_id=user_public_id)


@bridge.provide_op(ANALYTICS_GET_STATUS)
def get_status(*, provider, run_id, user=None, user_public_id=None, **_):
    return bridge.call(_backend(provider)['status'], run_id=run_id, user=user, user_public_id=user_public_id)
