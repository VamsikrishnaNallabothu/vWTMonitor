# Simple in-memory store for metrics/results
_metrics_store = {}

def store_metrics(test_id: str, metrics: dict):
    _metrics_store[test_id] = metrics

def get_metrics(test_id: str) -> dict:
    return _metrics_store.get(test_id, {})

def get_all_metrics() -> dict:
    return _metrics_store.copy() 