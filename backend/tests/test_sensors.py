import copy
import json
import math
import time
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.main import app
from app.models import ControlCommand, Goal, NavigationCommand
from app.navigation import OccupancyGrid
from app.sensors.lidar import raycast, VirtualLidar, VirtualLidarConfig
from app.sensors.manager import SensorManager
from app.simulator import RobotSimulator


def empty_grid():
    return OccupancyGrid(10, 10, 1.0, [0] * 100)


@pytest.mark.parametrize('angle,distance',[(0,8.5),(math.pi/2,8.5),(math.pi,1.5),(-math.pi/2,1.5)])
def test_empty_map_boundary_ranges(angle,distance):
    assert raycast(empty_grid(),1.5,1.5,angle,20) == pytest.approx((distance,True))


def test_obstacle_unknown_occupied_origin_and_no_return():
    grid=empty_grid()
    grid.data[1*10+4]=100
    assert raycast(grid,1.5,1.5,0) == (2.5,True)
    assert raycast(grid,1.5,1.5,0,2) == (2,False)
    assert raycast(grid,1.5,1.5,0,2.5) == (2.5,True)
    grid.data[1*10+4]=-1
    assert raycast(grid,1.5,1.5,0) == (2.5,True)
    assert raycast(grid,4.5,1.5,0) == (0,True)
    assert raycast(grid,-1,1.5,0) == (0,True)
    assert raycast(grid,10,1.5,math.pi) == (0,True)


def test_corner_tie_and_origin_on_cell_boundary():
    grid=empty_grid()
    grid.data[1*10+2]=100
    assert raycast(grid,1.5,1.5,math.pi/4)[0] == pytest.approx(math.sqrt(.5))
    grid.data[1*10+2]=0
    grid.data[1*10+0]=100
    assert raycast(grid,1,1.5,math.pi) == (0,True)


def test_grid_origin_and_known_warehouse_wall():
    grid=empty_grid();grid.origin=(-5,-5)
    assert raycast(grid,0,0,0,10) == (5,True)
    warehouse=OccupancyGrid()
    assert raycast(warehouse,1,1,0) == pytest.approx((2.2,True))
    assert raycast(warehouse,1,1,-math.pi/2) == pytest.approx((.8,True))


def test_scan_rotation_translation_metadata_and_determinism():
    grid=empty_grid();grid.data[1*10+4]=100
    sensor=VirtualLidar(grid)
    sensor.capture((1.5,1.5,0),'2026-11-20T00:00:00+00:00',10)
    first=sensor.snapshot(10)
    assert len(first['payload']['ranges']) == len(first['payload']['hits']) == 181
    assert first['payload']['ranges'][90] == 2.5
    assert first['metadata']['angle_increment'] == pytest.approx(math.pi/180)
    assert first['metadata']['range_max'] == 5
    assert first['metadata']['scan_time'] == .2
    assert first['metadata']['time_increment'] == 0
    assert first['source'] == 'SIMULATED'
    sensor.capture((2.5,1.5,0),'2026-11-20T00:00:00+00:00',10)
    assert sensor.snapshot(10)['payload']['ranges'][90] == 1.5
    sensor.capture((1.5,1.5,math.pi/2),'2026-11-20T00:00:00+00:00',10)
    rotated=sensor.snapshot(10)
    assert rotated['payload']['ranges'][90] == 5
    assert rotated['payload']['hits'][90] is False
    assert rotated['payload']['ranges'][0] == 2.5
    sensor.capture((1.5,1.5,0),'2026-11-20T00:00:00+00:00',10)
    assert sensor.snapshot(10)['payload'] == first['payload']
    detected=[r for r,hit in zip(first['payload']['ranges'],first['payload']['hits']) if hit]
    assert first['metadata']['min_obstacle_distance'] == min(detected)
    json.dumps(first,allow_nan=False)


@pytest.mark.parametrize('kwargs',[{'beam_count':1},{'beam_count':1000},{'update_hz':6},{'range_max':float('nan')},{'field_of_view':0}])
def test_sensor_configuration_bounds(kwargs):
    with pytest.raises(ValueError):VirtualLidarConfig(**kwargs)


def test_manager_rate_cache_staleness_and_camera_contract():
    manager=SensorManager(empty_grid(),(1.5,1.5,0),'2026-11-20T00:00:00+00:00',now=10)
    for i in range(1,101):
        manager.step(.1,(1.5,1.5,0),'2026-11-20T00:00:00+00:00',10+i*.1)
    frame=manager.snapshot(now=20)
    assert frame['lidar']['sequence'] == 51  # initial scan + exactly 5 per simulated second
    assert frame['lidar']['status'] == 'READY'
    assert manager.snapshot(now=21.1)['lidar']['status'] == 'STALE'
    assert manager.snapshot(now=21.1)['lidar']['freshness']['stale'] is True
    assert frame['camera']['status'] == 'NOT_CONNECTED'
    assert frame['camera']['source'] == 'PLACEHOLDER'
    assert frame['camera']['timestamp'] is None
    assert frame['camera']['metadata']['fps'] is None
    assert frame['camera']['metadata']['width'] is None
    assert frame['camera']['metadata']['stream_url'] is None
    assert frame['camera']['sequence'] == 0
    assert not hasattr(manager,'history')  # latest scan only, no accumulating frames
    assert 'payload' not in manager.snapshot(include_data=False)['lidar']
    sequence=frame['lidar']['sequence']
    manager.step(1,(1.5,1.5,0),'2026-11-20T00:00:00+00:00',21)
    assert manager.snapshot(now=21)['lidar']['sequence'] == sequence+1  # no catch-up burst


def test_sensor_reads_do_not_mutate_robot_map_or_mission():
    robot=RobotSimulator()
    robot.command(ControlCommand(type='control',linear=.1,angular=.3),'owner')
    robot.tick(.2)
    before=(robot.state.pose,list(robot.rpm),list(robot.counts),copy.deepcopy(robot.mission.snapshot()),list(robot.grid.data),robot.owner)
    for _ in range(10):
        bundle=robot.sensors.snapshot()
        bundle['lidar']['payload']['ranges'][0]=999
    after=(robot.state.pose,list(robot.rpm),list(robot.counts),robot.mission.snapshot(),robot.grid.data,robot.owner)
    assert before == after
    assert robot.sensors.snapshot()['lidar']['payload']['ranges'][0] != 999
    acquisition=robot.sensors.snapshot()['lidar']['payload']['acquisition_pose']
    assert (acquisition['x'],acquisition['y'],acquisition['yaw']) == robot.state.pose


def test_sensor_failure_does_not_disable_stop_navigation_or_collision_guard(monkeypatch):
    robot=RobotSimulator()
    def fail(*args):raise RuntimeError('injected sensor fault')
    monkeypatch.setattr(robot.sensors.lidar,'capture',fail)
    robot.command(NavigationCommand(type='navigation',action='start',goal=Goal(x=2,y=1)),'owner')
    robot.tick(.2)
    assert robot.mission.status == 'running'
    assert robot.sensors.snapshot()['lidar']['status'] == 'ERROR'
    assert robot.sensors.snapshot()['lidar']['payload'] is None
    for _ in range(5):
        robot.command(ControlCommand(type='heartbeat'),'owner');robot.tick(.2)
    assert sum('scan generation failed' in event['message'] for event in robot.events) == 1
    robot.command(ControlCommand(type='stop'),'observer')
    assert robot.rpm == robot.targets() == [0,0]
    assert robot.mission.status == 'idle'
    for _ in range(200):
        robot.command(ControlCommand(type='control',linear=.6),'owner');robot.tick(.1)
        assert robot.grid.free(*robot.state.pose[:2])
        if robot.collision_origin is not None:break
    assert robot.collision_origin is not None
    assert robot.rpm == [0,0]


def test_sensor_http_and_readonly_websocket_are_shared_and_not_motion_owners():
    with TestClient(app) as client:
        summary=client.get('/api/sensors').json()
        assert summary['lidar']['source'] == 'SIMULATED'
        assert 'payload' not in summary['lidar']
        full=client.get('/api/sensors/lidar').json()
        assert full['payload']['ranges'][90] == pytest.approx(2.2,abs=.0001)
        assert client.get('/api/sensors/camera').json()['metadata']['fps'] is None
        robot=app.state.robot
        robot.command(NavigationCommand(type='navigation',action='start',goal=Goal(x=2,y=1)),'owner')
        with client.websocket_connect('/ws/sensors') as ws:
            message=ws.receive_json()
            assert message['type'] == 'sensors' and message['simulation'] is True
            assert message['session_id'] == robot.session_id
        assert robot.owner == 'owner'
        assert robot.mission.status == 'running'
        with client.websocket_connect('/ws/sensors') as ws:
            ws.receive_json()
            ws.send_json({'type':'stop'})
            with pytest.raises(WebSocketDisconnect) as exc:
                while True:ws.receive_json()
            assert exc.value.code == 1008
        assert robot.mission.status == 'running'
        assert robot.snapshot()['diagnostics']['interfaces']['ros2']['source'] == 'disabled'
        assert robot.snapshot()['diagnostics']['interfaces']['uart']['source'] == 'disabled'
        robot.command(ControlCommand(type='stop'),'owner')


def test_sensor_websocket_rejects_untrusted_origin():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect('/ws/sensors',headers={'origin':'https://untrusted.example'}):pass
        assert exc.value.code == 1008


def test_open_space_no_return_is_not_a_fake_obstacle_and_payload_is_bounded():
    grid=OccupancyGrid(20,20,1,[0]*400)
    sensor=VirtualLidar(grid)
    sensor.capture((10,10,0),'2026-11-20T00:00:00+00:00',10)
    frame=sensor.snapshot(10)
    assert frame['payload']['ranges'] == [5.0]*181
    assert frame['payload']['hits'] == [False]*181
    assert frame['metadata']['min_obstacle_distance'] is None
    assert frame['metadata']['hit_count'] == 0
    assert len(json.dumps(frame,allow_nan=False).encode()) < 8192
    robot=RobotSimulator()
    summary=robot.snapshot()['sensors']
    assert 'ranges' not in json.dumps(summary)
    assert len(json.dumps(summary).encode()) < 4096


def test_scan_tracks_authoritative_pose_while_robot_translates_and_rotates():
    robot=RobotSimulator()
    initial=robot.state.pose
    for _ in range(5):
        robot.command(ControlCommand(type='control',linear=.1,angular=.4),'owner')
        robot.tick(.2)
        frame=robot.sensors.snapshot()['lidar']
        pose=frame['payload']['acquisition_pose']
        assert (pose['x'],pose['y'],pose['yaw']) == robot.state.pose
        expected,hit=raycast(robot.grid,pose['x'],pose['y'],pose['yaw'],5)
        assert frame['payload']['ranges'][90] == pytest.approx(expected,abs=.0001)
        assert frame['payload']['hits'][90] is hit
    assert robot.state.pose[0] > initial[0]
    assert robot.state.pose[2] > initial[2]
    robot.command(ControlCommand(type='stop'),'owner')
    robot.tick(.2)
    assert robot.rpm == [0,0]
