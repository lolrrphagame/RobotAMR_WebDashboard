"""Static serving smoke tests; all lifespans use the isolated conftest paths."""
import re
import pytest
from fastapi.testclient import TestClient
from app.production import create_app


def test_production_serves_only_built_assets_and_known_pages():
    with TestClient(create_app(),base_url='http://127.0.0.1') as client:
        html=client.get('/')
        assert html.status_code==200
        asset=re.search(r'src="(/assets/[^\"]+\.js)"',html.text).group(1)
        assert client.get(asset).status_code==200
        for page in ('overview','manual-control','navigation','missions','sensors','diagnostics','settings'):
            assert client.get('/'+page).text==html.text
        for path in ('/docs','/redoc','/openapi.json','/src/main.tsx','/@vite/client','/.env','/backend/data/robot-config.json','/api/missing','/ws/missing','/assets/missing.js','/assets/secret.map','/assets/%2e%2e/%2e%2e/.env'):
            assert client.get(path).status_code==404
        assert 'OPERATOR_PASSWORD_HASH' not in html.text
        assert client.get('/api/auth/session').json()['role']=='operator'
        with client.websocket_connect('/ws/telemetry',headers={'origin':'http://127.0.0.1:5173'}) as ws:
            assert ws.receive_json()['simulation'] is True
        assert client.get('/api/health').json()['hardware_enabled'] is False


def test_production_keeps_security_guards():
    with TestClient(create_app(),base_url='http://127.0.0.1',client=('192.168.1.22',33000)) as client:
        assert client.get('/').status_code==403
    with TestClient(create_app(),base_url='http://127.0.0.1') as client:
        assert client.get('/',headers={'host':'evil.test'}).status_code==400
        assert client.post('/api/configuration',headers={'origin':'https://evil.test'},json={'type':'configuration','action':'reset_home'}).status_code==403


def test_production_factory_rejects_lan(monkeypatch):
    monkeypatch.setenv('APP_MODE','lan')
    with pytest.raises(ValueError,match='loopback-only'):create_app()
