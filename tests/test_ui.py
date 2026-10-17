import pytest
from fastapi.testclient import TestClient
from app import create_app
from config import Settings
from services.tasks import TaskService
from unittest.mock import Mock

def test_nicegui_routes_render_without_database_or_keys():
    service=TaskService(Mock(),Mock(),Settings())
    with TestClient(create_app(service)) as client:
        response=client.get('/')
        assert response.status_code==200
        assert 'AgentScout' in response.text
        assert '研究需求' in response.text
        assert client.get('/evaluations').status_code==200
        assert client.get('/health/live').json()=={'status':'alive'}
