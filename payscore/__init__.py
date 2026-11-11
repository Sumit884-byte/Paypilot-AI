"""PayScore AI components (Week 1): credit-scoring baseline, schema, API."""

from ._native import ensure_openmp

__version__ = "0.1.0"

# Before any LightGBM import: serverless Linux runtimes ship without libgomp
ensure_openmp()
