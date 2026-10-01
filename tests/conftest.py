import pytest

from evals.sandbox import isolated_app


@pytest.fixture
def client():
    with isolated_app() as test_client:
        yield test_client
