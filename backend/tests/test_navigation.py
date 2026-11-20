import math
import time
import pytest
from app.drive import DifferentialDrive, DriveConfig, wrap_angle
from app.models import ControlCommand, Goal, NavigationCommand, WaypointCommand
from app.navigation import OccupancyGrid, plan_path
from app.simulator import AUTONOMOUS_TIMEOUT, RobotSimulator


def nav(action, **kwargs):
    return NavigationCommand(type="navigation", action=action, **kwargs)


def run_until_finished(robot, limit=2000):
    progress = 0
    for _ in range(limit):
        robot.command(ControlCommand(type="heartbeat"), robot.owner)
        robot.tick(0.1)
        assert max(map(abs, robot.rpm)) <= 40.000001
        assert robot.grid.free(*robot.state.pose[:2])
        assert robot.mission.progress >= progress
        progress = robot.mission.progress
        if robot.mission.status != "running":
            return
    pytest.fail("Path follower did not finish within simulated time limit")


@pytest.mark.parametrize("linear,angular", [(0.1,0), (-0.1,0), (0,0.8), (0,-0.8), (0.05,0.3)])
def test_forward_inverse_roundtrip(linear, angular):
    drive = DifferentialDrive()
    assert drive.forward(drive.inverse(linear, angular)) == pytest.approx((linear, angular))


@pytest.mark.parametrize("linear", [-0.6,-0.18,0,0.18,0.6])
@pytest.mark.parametrize("angular", [-2,-1,0,1,2])
def test_combined_rpm_limit_preserves_curvature(linear, angular):
    drive = DifferentialDrive()
    limited = drive.inverse(linear, angular)
    assert max(map(abs, limited)) <= 40.000001
    v, w = drive.forward(limited)
    if linear and angular:
        assert v / w == pytest.approx(linear / angular)
    for _ in range(20):
        limited = drive.accelerate(limited, [40,-40], 0.1)
        assert max(map(abs, limited)) <= 40


def test_pose_integration_straight_spin_arc_and_reverse():
    drive = DifferentialDrive()
    assert drive.integrate((0,0,0), drive.inverse(.1,0), 2) == pytest.approx((.2,0,0))
    assert drive.integrate((0,0,math.pi/2), drive.inverse(.1,0), 2) == pytest.approx((0,.2,math.pi/2))
    assert drive.integrate((0,0,0), drive.inverse(-.1,0), 2) == pytest.approx((-.2,0,0))
    assert drive.integrate((2,3,0), drive.inverse(0,.5), 2) == pytest.approx((2,3,1))
    x,y,yaw = drive.integrate((0,0,0), drive.inverse(.05,.2), 2)
    assert (x,y,yaw) == pytest.approx((.25*math.sin(.4), .25*(1-math.cos(.4)), .4))


def test_acceleration_deceleration_and_encoder_polarity():
    drive = DifferentialDrive()
    assert drive.accelerate([0,0],[40,40],.1) == [6,6]
    assert drive.accelerate([40,40],[0,0],.1) == [34,34]
    robot = RobotSimulator(DriveConfig(encoder_polarity=(-1,1)))
    robot.command(ControlCommand(type="control", linear=.1), "driver")
    robot.tick(.1)
    assert robot.state.pose[0] > 1
    assert robot.state.pose[1] == pytest.approx(1)
    motors = robot.snapshot()["motors"]
    assert motors[0]["encoder_count"] > 0
    assert motors[0]["raw_encoder_count"] == -motors[0]["encoder_count"]
    assert motors[1]["raw_encoder_count"] == motors[1]["encoder_count"]
    with pytest.raises(ValueError):
        DriveConfig(encoder_polarity=(0,1))


def test_astar_routes_around_wall_and_rejects_occupied_or_unreachable():
    grid = OccupancyGrid()
    path = plan_path(grid, (1,1), (4.5,1))
    assert not grid.segment_free((1,1),(4.5,1))
    assert min(y for _,y in path) < .8-grid.clearance or max(y for _,y in path) > 3.8+grid.clearance
    assert all(grid.segment_free(a,b) for a,b in zip(path,path[1:]))
    with pytest.raises(ValueError):
        plan_path(grid,(1,1),(3.3,2))
    with pytest.raises(ValueError):
        plan_path(grid,(1,1),(.25,.25))
    # A complete dividing wall makes two otherwise valid cells unreachable.
    data = [0]*100
    for y in range(10):
        data[y*10+5] = 100
    sealed = OccupancyGrid(10,10,1,data)
    with pytest.raises(ValueError, match="No collision-free"):
        plan_path(sealed,(2,2),(8,2))


def test_waypoint_management_and_atomic_planning():
    robot = RobotSimulator()
    for name, goal in [("A",Goal(x=2,y=1)),("B",Goal(x=2,y=2)),("C",Goal(x=1,y=2))]:
        assert robot.command(WaypointCommand(type="waypoint",name=name,goal=goal),"a")
    assert list(robot.mission.waypoints) == ["A","B","C"]
    robot.command(nav("sequence",waypoints=["A","B","C"]),"a")
    assert [goal.name for goal in robot.mission.goals] == ["A","B","C"]
    run_until_finished(robot)
    assert robot.mission.status == "completed"
    assert math.dist(robot.state.pose[:2],(1,2)) < .05
    robot.command(WaypointCommand(type="waypoint",action="delete",name="C"),"a")
    with pytest.raises(ValueError,match="Save every"):
        robot.command(nav("sequence",waypoints=["C"]),"a")
    with pytest.raises(ValueError):
        robot.command(nav("start",goal=Goal(x=3.4,y=2)),"a")
    assert robot.mission.status == "completed"


def test_follower_reaches_goal_with_heading_and_returns_home():
    robot = RobotSimulator()
    goal=Goal(x=4.5,y=1,yaw=math.pi/2)
    robot.command(nav("start",goal=goal),"a")
    run_until_finished(robot)
    assert robot.mission.status == "completed"
    assert robot.mission.progress == 100
    assert math.dist(robot.state.pose[:2],(goal.x,goal.y)) < .05
    assert abs(wrap_angle(robot.state.pose[2]-goal.yaw)) < .04
    robot.command(nav("home"),"a")
    run_until_finished(robot)
    assert robot.mission.status == "completed"
    assert math.dist(robot.state.pose[:2],(1,1)) < .05


def test_manual_autonomous_arbitration_pause_resume_and_global_stop():
    robot = RobotSimulator()
    robot.command(ControlCommand(type="control",linear=.1),"a")
    assert not robot.command(nav("start",goal=Goal(x=2,y=1)),"a")
    robot.command(ControlCommand(type="release"),"a")
    assert robot.command(nav("start",goal=Goal(x=2,y=1)),"a")
    assert not robot.command(ControlCommand(type="control",linear=.1),"a")
    assert not robot.command(nav("pause"),"b")
    robot.command(ControlCommand(type="release"),"a")
    assert robot.mission.status == "running"
    robot.tick(.1)
    robot.command(nav("pause"),"a")
    pose=robot.state.pose
    robot.tick(.5)
    assert robot.state.pose == pose
    assert robot.rpm == [0,0]
    assert robot.mode == "AUTONOMOUS"
    robot.command(nav("resume"),"a")
    robot.tick(.1)
    robot.command(ControlCommand(type="stop"),"b")
    assert robot.rpm == [0,0]
    assert robot.targets() == [0,0]
    assert robot.mission.status == "cancelled"
    robot.tick(.1)
    assert robot.mode == "STANDBY"


def test_disconnect_heartbeat_timeout_and_reconnection(monkeypatch):
    robot=RobotSimulator()
    robot.command(nav("start",goal=Goal(x=2,y=1)),"a")
    robot.disconnect("observer")
    assert robot.mission.status == "running"
    robot.disconnect("a")
    assert robot.mission.status == "paused"
    assert robot.owner is None
    assert robot.rpm == [0,0]
    robot.command(nav("resume"),"b")
    monkeypatch.setattr("app.simulator.time.monotonic",lambda: robot.last_lease+AUTONOMOUS_TIMEOUT+.01)
    robot.tick(.1)
    assert robot.mission.status == "paused"
    assert robot.owner is None
    assert robot.rpm == [0,0]


def test_collision_guard_blocks_manual_motion_without_tunneling():
    robot=RobotSimulator()
    for _ in range(200):
        robot.command(ControlCommand(type="control",linear=.6),"a")
        robot.tick(.1)
        assert robot.grid.free(*robot.state.pose[:2])
        if robot.mission.status == "blocked":
            break
    assert robot.mission.status == "blocked"
    assert robot.state.pose[0] < 3.2-robot.grid.clearance
    assert robot.rpm == [0,0]


def test_resume_preserves_completed_waypoints_and_progress():
    robot=RobotSimulator()
    robot.mission.save("A",Goal(x=1.3,y=1))
    robot.mission.save("B",Goal(x=1.5,y=1.5))
    robot.command(nav("sequence",waypoints=["A","B"]),"a")
    for _ in range(300):
        robot.command(ControlCommand(type="heartbeat"),"a")
        robot.tick(.1)
        if robot.mission.leg == 1:
            break
    assert robot.mission.leg == 1
    progress=robot.mission.progress
    robot.command(nav("pause"),"a")
    robot.command(nav("resume"),"a")
    state=robot.snapshot()["navigation"]
    assert state["waypoint_index"] == 2
    assert state["waypoint_count"] == 2
    assert state["progress"] >= round(progress,1)
    run_until_finished(robot)
    assert robot.mission.status == "completed"
