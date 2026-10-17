from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from app import create_app
from config import Settings
from services.tasks import TaskService
from storage.repository import Conflict, NotFound


@pytest.fixture
def api():
    repo = Mock()
    repo.create_task.return_value = 't1'
    repo.get_task.return_value = {'id': 't1', 'current_attempt': {'id': 'a1'}}
    repo.reserve_dispatch.return_value = True
    publish = Mock()
    service = TaskService(repo, publish, Settings())
    with TestClient(create_app(service, with_ui=False)) as client:
        yield client, repo, publish


def test_submit_requires_idempotency_key_and_rejects_unknown_fields(api):
    client, repo, publish = api
    assert client.post('/api/v1/tasks', json={'input_text': 'study'}).status_code == 422
    assert client.post('/api/v1/tasks', headers={'Idempotency-Key': 'k'}, json={'input_text': 'study', 'api_key': 'bad'}).status_code == 422
    repo.create_task.assert_not_called()
    publish.assert_not_called()


def test_submit_enqueues_identifier_only(api):
    client, repo, publish = api
    response = client.post('/api/v1/tasks', headers={'Idempotency-Key': 'k'}, json={'input_text': 'study'})
    assert response.status_code == 202 and response.json()['id'] == 't1'
    publish.assert_called_once_with('a1')
    repo.mark_queued.assert_called_once_with('a1')


def test_broker_failure_keeps_durable_task(api):
    client, repo, publish = api
    publish.side_effect = ConnectionError('unavailable')
    assert client.post('/api/v1/tasks', headers={'Idempotency-Key': 'k'}, json={'input_text': 'study'}).status_code == 202
    repo.mark_queued.assert_not_called()


def test_validation_and_not_found_errors(api):
    client, repo, publish = api
    assert client.get('/api/v1/tasks?limit=1001').status_code == 422
    assert client.get('/api/v1/tasks?status=unknown').status_code == 422
    repo.get_task.side_effect = NotFound('missing')
    assert client.get('/api/v1/tasks/missing').status_code == 404
    repo.retry.side_effect = Conflict('active')
    assert client.post('/api/v1/tasks/t1/retry').status_code == 409


def test_real_submission_requires_configured_provider(api):
    client, repo, publish = api
    response = client.post('/api/v1/tasks', headers={'Idempotency-Key': 'k'}, json={'input_text': 'study', 'mock': False})
    assert response.status_code == 409
    publish.assert_not_called()
