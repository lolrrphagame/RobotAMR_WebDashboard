from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest
from app.main import app


def receive_type(ws, kind):
    for _ in range(30):
        message = ws.receive_json()
        if message["type"] == kind:
            return message
    raise AssertionError(f"Did not receive {kind}")


def receive_mode(ws, mode):
    for _ in range(30):
        message = receive_type(ws, "telemetry")
        if message["mode"] == mode:
            return message
    raise AssertionError(f"Did not reach {mode}")


def test_http_status_and_websocket_control_stop():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok", "simulation": True, "hardware_enabled": False}
        status = client.get("/api/robot/status")
        assert status.status_code == 200
        assert status.json()["simulation"] is True
        with client.websocket_connect("/ws/telemetry") as ws:
            assert ws.receive_json()["mode"] == "STANDBY"
            ws.send_json({"type": "control", "linear": 0.2, "angular": 0})
            data = receive_mode(ws, "MANUAL")
            assert data["motors"][0]["target_rpm"] > 0
            ws.send_json({"type": "stop"})
            data = receive_mode(ws, "STANDBY")
            assert data["motors"][0]["actual_rpm"] == 0


def test_disconnect_and_invalid_payload_fail_closed():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            ws.receive_json()
            ws.send_json({"type": "control", "linear": 0.3})
            receive_mode(ws, "MANUAL")
            ws.send_text("not json")
            assert "Invalid" in receive_type(ws, "error")["message"]
            assert client.get("/api/robot/status").json()["mode"] == "STANDBY"
            ws.send_json({"type": "control", "linear": -0.2})
            receive_mode(ws, "MANUAL")
        # Entering another WS yields to disconnect cleanup without a timing sleep.
        with client.websocket_connect("/ws/telemetry") as observer:
            assert observer.receive_json()["mode"] == "STANDBY"
        assert client.get("/api/robot/status").json()["motors"][0]["target_rpm"] == 0


def test_untrusted_browser_origin_rejected():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/telemetry", headers={"origin": "https://untrusted.example"}):
                pass
        assert exc.value.code == 1008


def test_map_navigation_websocket_and_http_share_one_state():
    with TestClient(app) as client:
        grid = client.get("/api/map").json()
        assert grid["frame_id"] == "map"
        assert len(grid["data"]) == grid["width"] * grid["height"]
        assert set(grid["data"]) == {0, 100}
        with client.websocket_connect("/ws/telemetry") as ws:
            initial = ws.receive_json()
            assert initial["pose"] == client.get("/api/robot/status").json()["pose"]
            ws.send_json({"type":"waypoint","name":"A","goal":{"x":2,"y":1,"yaw":0}})
            receive_type(ws,"ack")
            ws.send_json({"type":"navigation","action":"sequence","waypoints":["A"]})
            receive_type(ws,"ack")
            assert receive_mode(ws,"AUTONOMOUS")["navigation"]["status"] == "running"
            ws.send_json({"type":"control","linear":.1})
            assert "reserved" in receive_type(ws,"error")["message"]
            ws.send_json({"type":"navigation","action":"pause"})
            receive_type(ws,"ack")
            frame = receive_type(ws,"telemetry")
            http = client.get("/api/robot/status").json()
            assert frame["pose"] == http["pose"]
            assert frame["navigation"] == http["navigation"]
            assert http["navigation"]["status"] == "paused"
            assert http["motors"][0]["actual_rpm"] == 0
            ws.send_json({"type":"navigation","action":"resume"})
            receive_type(ws,"ack")
        with client.websocket_connect("/ws/telemetry") as observer:
            frame = observer.receive_json()
            assert frame["navigation"]["status"] == "paused"
            observer.send_json({"type":"stop"})
            receive_type(observer,"ack")
            assert client.get("/api/robot/status").json()["navigation"]["status"] == "idle"
