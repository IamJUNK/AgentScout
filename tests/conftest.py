import os
import socket
import pytest

# Never read developer API credentials during collection or test execution.
os.environ['AGENTSCOUT_NO_DOTENV'] = '1'
for name in ('LLM_API_KEY', 'TAVILY_API_KEY', 'EMBEDDING_API_KEY'):
    os.environ.pop(name, None)

@pytest.fixture(autouse=True)
def disallow_external_network(monkeypatch, request):
    if request.node.get_closest_marker('integration'):
        return
    original = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {'127.0.0.1','::1','localhost'}:
            raise AssertionError('External network is disabled in unit tests')
        return original(sock, address)
    monkeypatch.setattr(socket.socket, 'connect', connect)
