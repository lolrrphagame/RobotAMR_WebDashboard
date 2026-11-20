import csv
import io
import json
import math
import pytest
from fastapi.testclient import TestClient
from app.configuration import ConfigurationStore, ConfigurationError, ConfigurationConflict
from app.main import app
from app.models import ConfigurationCommand, ControlCommand, Goal, NavigationCommand, WaypointCommand
from app.simulator import RobotSimulator, COMMAND_TIMEOUT


def home_command(action="set_home", **kwargs):
    return ConfigurationCommand(type="configuration", action=action, **kwargs)


def finish(robot):
    for _ in range(2500):
        robot.command(ControlCommand(type="heartbeat"),"owner")
        robot.tick(.1)
        assert robot.grid.free(*robot.state.pose[:2])
        assert max(map(abs,robot.rpm)) <= 40+1e-9
        if robot.mission.status != "running":
            break
    assert robot.mission.status == "idle"
    assert robot.mission.last_result["status"] == "completed"


def test_saved_home_initializes_new_session_but_never_teleports_current_robot(tmp_path):
    store=ConfigurationStore(tmp_path/"config.json")
    robot=RobotSimulator(store=store)
    pose,counts,trail=robot.state.pose,list(robot.counts),list(robot.state.trajectory)
    robot.command(home_command(goal=Goal(x=2,y=2,yaw=.7)),"owner")
    assert robot.state.pose == pose
    assert robot.counts == counts
    assert list(robot.state.trajectory) == trail
    assert robot.snapshot()["home"] == {"x":2,"y":2,"yaw":.7}
    restored=RobotSimulator(store=store)
    assert restored.state.pose == (2,2,.7)
    assert restored.rpm == [0,0]
    assert restored.counts == [0,0]
    assert list(restored.state.trajectory) == [(2,2)]
    assert restored.mission.status == "idle"
    robot.command(NavigationCommand(type="navigation",action="home"),"owner")
    finish(robot)
    assert math.dist(robot.state.pose[:2],(2,2)) < .035
    assert abs(robot.state.pose[2]-.7) < .035


def test_current_pose_home_and_reset_default_persist(tmp_path):
    store=ConfigurationStore(tmp_path/"config.json")
    robot=RobotSimulator(store=store)
    robot.command(ControlCommand(type="control",linear=.1,angular=.2),"owner")
    robot.tick(.1)
    before=robot.state.pose
    rpm,counts=list(robot.rpm),list(robot.counts)
    robot.command(home_command("current_home"),"owner")
    assert robot.state.pose == before
    assert robot.rpm == rpm and robot.counts == counts
    assert RobotSimulator(store=store).state.pose == pytest.approx(before)
    robot.command(home_command("reset_home"),"owner")
    assert robot.state.pose == before
    assert RobotSimulator(store=store).state.pose == (1,1,0)


@pytest.mark.parametrize("position",[(3.4,2),(.2,.2),(7.9,5.9)])
def test_occupied_or_unsafe_home_rejected_without_memory_or_disk_change(tmp_path,position):
    store=ConfigurationStore(tmp_path/"config.json")
    robot=RobotSimulator(store=store)
    robot.command(home_command("reset_home"),"owner")
    original=store.path.read_bytes()
    with pytest.raises(ConfigurationError,match="footprint clearance"):
        robot.command(home_command(goal=Goal(x=position[0],y=position[1])),"owner")
    assert store.path.read_bytes() == original
    assert robot.state.pose == (1,1,0)
    assert robot.configuration.value.home.x == 1


@pytest.mark.parametrize("paused",[False,True])
def test_home_rejected_during_active_or_paused_mission_without_changing_ownership(paused):
    robot=RobotSimulator()
    robot.command(NavigationCommand(type="navigation",action="start",goal=Goal(x=2,y=1)),"owner")
    if paused:
        robot.command(NavigationCommand(type="navigation",action="pause"),"owner")
    status=robot.mission.status
    for command in [home_command(goal=Goal(x=2,y=2)),home_command("current_home"),home_command("reset_home")]:
        with pytest.raises(ConfigurationConflict):
            robot.command(command,"other")
        assert robot.mission.status == status
        assert robot.owner == "owner"
        assert robot.configuration.value.home.x == 1


def test_waypoint_headings_overwrite_delete_and_sequence_survive_restart(tmp_path):
    store=ConfigurationStore(tmp_path/"config.json")
    robot=RobotSimulator(store=store)
    for name,x,y,yaw in [("A",2,1,.2),("B",2,2,.4),("C",1,2,.6)]:
        robot.command(WaypointCommand(type="waypoint",name=name,goal=Goal(x=x,y=y,yaw=yaw)),"owner")
    robot=RobotSimulator(store=store)
    assert [robot.mission.waypoints[n].yaw for n in "ABC"] == [.2,.4,.6]
    robot.command(NavigationCommand(type="navigation",action="sequence",waypoints=["A","B","C"]),"owner")
    finish(robot)
    assert math.dist(robot.state.pose[:2],(1,2)) < .035
    robot.command(WaypointCommand(type="waypoint",name="A",goal=Goal(x=2.2,y=1.2,yaw=-.4)),"owner")
    robot.command(WaypointCommand(type="waypoint",action="delete",name="B"),"owner")
    restored=RobotSimulator(store=store)
    assert restored.mission.waypoints["A"].yaw == -.4
    assert restored.mission.waypoints["A"].x == 2.2
    assert set(restored.mission.waypoints) == {"A","C"}


def test_invalid_loaded_poses_are_filtered_and_original_file_preserved(tmp_path):
    path=tmp_path/"config.json"
    payload={"version":1,"home":{"x":3.4,"y":2,"yaw":0},"waypoints":{
        "A":{"x":2,"y":1,"yaw":.8},"B":{"x":3.4,"y":2,"yaw":0},"C":{"x":1,"y":2,"yaw":float('nan')}}}
    path.write_text(json.dumps(payload))
    before=path.read_bytes()
    robot=RobotSimulator(store=ConfigurationStore(path))
    assert robot.state.pose == (1,1,0)
    assert set(robot.mission.waypoints) == {"A"}
    assert len(robot.configuration.warnings) == 3
    assert path.read_bytes() == before


@pytest.mark.parametrize("content",['{not json}', '{"version":99}', '[]'])
def test_corrupt_or_unsupported_configuration_falls_back_safely(tmp_path,content):
    path=tmp_path/"config.json";path.write_text(content)
    robot=RobotSimulator(store=ConfigurationStore(path))
    assert robot.state.pose == (1,1,0)
    assert robot.configuration.warnings
    assert path.read_text() == content


def test_atomic_replace_failure_preserves_configuration_and_motion(tmp_path,monkeypatch):
    store=ConfigurationStore(tmp_path/"config.json")
    robot=RobotSimulator(store=store)
    robot.command(home_command("reset_home"),"owner")
    old=store.path.read_bytes()
    def fail(*args):
        raise OSError("simulated disk failure")
    monkeypatch.setattr("app.configuration.os.replace",fail)
    with pytest.raises(ConfigurationError,match="no change applied"):
        robot.command(home_command(goal=Goal(x=2,y=2)),"owner")
    with pytest.raises(ConfigurationError):
        robot.command(WaypointCommand(type="waypoint",name="A",goal=Goal(x=2,y=1)),"owner")
    assert store.path.read_bytes() == old
    assert robot.state.pose == (1,1,0)
    assert robot.configuration.value.home.x == 1
    assert robot.mission.waypoints == {}
    assert list(tmp_path.glob('.robot-config-*.tmp')) == []


def test_motor_diagnostics_are_consistent_and_do_not_invent_pi_or_uart_data():
    robot=RobotSimulator()
    robot.command(ControlCommand(type="control",linear=.6,angular=.4),"owner")
    robot.tick(.1)
    frame=robot.snapshot();diag=frame["diagnostics"]
    assert diag["saturation"]["active"] is True
    assert diag["motion"]["requested"]["linear"] == .6
    assert diag["motion"]["limited"]["linear"] < .6
    assert diag["motion"]["measured"]["linear"] == frame["linear_velocity"]
    for i,motor in enumerate(frame["motors"]):
        assert motor["tracking_error_rpm"] == pytest.approx(motor["target_rpm"]-motor["actual_rpm"])
        assert motor["wheel_velocity"] == pytest.approx(robot.rpm[i]*2*math.pi*.0435/60)
        assert motor["travel_distance"] == pytest.approx(robot.counts[i]/3960*2*math.pi*.0435)
        assert all(motor["pi"][key] is None for key in ['kp','ki','pwm','control_error','integral_term'])
    assert diag["interfaces"]["uart"]["connected"] is False
    assert diag["interfaces"]["uart"]["tx_bytes"] is None
    assert diag["interfaces"]["ros2"]["last_message_at"] is None
    row=robot.history[-1]
    assert row['left_error_rpm'] == frame['motors'][0]['tracking_error_rpm']
    assert row['right_encoder_count'] == frame['motors'][1]['encoder_count']


def test_watchdog_stop_and_disconnect_statuses_preserve_safety(monkeypatch):
    robot=RobotSimulator()
    robot.command(ControlCommand(type="control",linear=.1),"owner")
    monkeypatch.setattr("app.simulator.time.monotonic",lambda:robot.last_command+COMMAND_TIMEOUT+.01)
    robot.tick(.1)
    assert robot.safety["watchdog"] == "expired"
    assert robot.rpm == [0,0]
    robot.command(ControlCommand(type="stop"),"observer")
    assert robot.snapshot()["diagnostics"]["safety"]["stop_active"] is True
    robot.command(NavigationCommand(type="navigation",action="start",goal=Goal(x=2,y=1)),"owner")
    assert robot.safety["stop_active"] is False
    robot.disconnect("owner")
    assert robot.rpm == [0,0]
    assert robot.mission.status == "paused"
    assert robot.safety["watchdog"] == "disconnected"


def test_configuration_api_persists_between_lifespans_and_invalid_input_does_not_mutate():
    with TestClient(app) as client:
        response=client.post('/api/configuration',json={'type':'configuration','action':'set_home','goal':{'x':2,'y':2,'yaw':.3}})
        assert response.status_code == 200
        assert client.get('/api/robot/status').json()['pose']['x'] == 1
        assert client.post('/api/waypoints',json={'type':'waypoint','name':'A','goal':{'x':2,'y':1,'yaw':.4}}).status_code == 200
        assert client.post('/api/configuration',json={'type':'configuration','action':'set_home','goal':{'x':3.4,'y':2}}).status_code == 400
        assert client.post('/api/configuration',json={'type':'configuration','action':'set_home','goal':{'x':20,'y':2}}).status_code == 422
    with TestClient(app) as client:
        frame=client.get('/api/robot/status').json()
        assert frame['pose']['x'] == 2 and frame['pose']['y'] == 2
        assert frame['pose']['yaw'] == .3
        assert frame['navigation']['waypoints']['A']['yaw'] == .4
        robot=app.state.robot
        robot.command(NavigationCommand(type='navigation',action='start',goal=Goal(x=2,y=1)),'owner')
        assert client.post('/api/configuration',json={'type':'configuration','action':'reset_home'}).status_code == 409
        assert robot.mission.status == 'running'
        assert robot.owner == 'owner'


def test_event_filter_csv_and_history_are_bounded_and_consistent():
    with TestClient(app) as client:
        robot=app.state.robot
        for i in range(80):
            robot.log('info',f'Sample event {i}')
        robot.log('warning','Wheel collision, test "quoted"')
        robot.log('error','=SUM(A1:A2)')
        result=client.get('/api/events',params={'level':'warning','q':'COLLISION'}).json()
        assert len(result['events']) == 1
        response=client.get('/api/events',params={'level':'warning','q':'collision','format':'csv'})
        rows=list(csv.DictReader(io.StringIO(response.text)))
        assert rows[0]['message'] == 'Wheel collision, test "quoted"'
        assert rows[0]['time'].endswith('+00:00')
        errors=client.get('/api/events',params={'level':'error','format':'csv'}).text
        assert "'=SUM" in errors
        assert len(client.get('/api/events').json()['events']) == 60
        for _ in range(620):robot.tick(.1)
        history=client.get('/api/diagnostics/history').json()
        assert len(history['samples']) == 600
        csv_rows=list(csv.DictReader(io.StringIO(client.get('/api/diagnostics/history?format=csv').text)))
        assert len(csv_rows) == 600
        assert float(csv_rows[-1]['left_actual_rpm']) == history['samples'][-1]['left_actual_rpm']
        assert csv_rows[-1]['source'] == 'simulation'
        assert client.get('/api/diagnostics/history?limit=601').status_code == 422


def test_measurement_timestamps_history_and_session_ids_are_consistent():
    robot=RobotSimulator()
    robot.tick(.1)
    frame=robot.snapshot()
    assert frame['timestamp'] == robot.history[-1]['timestamp']
    assert frame['session_id'] == robot.history[-1]['session_id']
    assert robot.snapshot()['timestamp'] == frame['timestamp']
    assert robot.snapshot()['health'] == frame['health']
    assert RobotSimulator().session_id != robot.session_id


def test_manual_disconnect_status_remains_disconnected():
    robot=RobotSimulator()
    robot.command(ControlCommand(type='control',linear=.1),'owner')
    robot.tick(.1)
    robot.disconnect('owner')
    assert robot.safety['watchdog'] == 'disconnected'
    assert robot.rpm == robot.targets() == [0,0]
