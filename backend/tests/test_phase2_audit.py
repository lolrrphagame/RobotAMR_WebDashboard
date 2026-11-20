"""Phase 2 finalization regressions; no hardware and no wall-clock sleeps."""
import math
import pytest
from app.drive import DriveConfig, ENCODER_CPR, MAX_RPM, wrap_angle
from app.models import ControlCommand, Goal, NavigationCommand, WaypointCommand
from app.navigation import OccupancyGrid
from app.simulator import RobotSimulator
from app.state import HOME, CHASSIS_SIZE


def command(robot, **kwargs):
    return robot.command(ControlCommand(type="control", **kwargs), "driver")


def navigate(robot, action, **kwargs):
    assert robot.command(NavigationCommand(type="navigation", action=action, **kwargs), "driver")


def assert_idle(robot):
    state = robot.snapshot()
    nav = state["navigation"]
    assert nav["status"] == "idle"
    assert nav["path"] == []
    assert nav["destination"] is None
    assert nav["current_waypoint"] is None
    assert nav["waypoint_count"] == 0
    assert nav["waypoint_index"] == 0
    assert nav["progress"] == 0
    assert robot.targets() == [0,0]
    assert robot.rpm == [0,0]
    assert robot.owner is None
    assert state["mode"] == "STANDBY"


def finish(robot, destination):
    for _ in range(2500):
        robot.command(ControlCommand(type="heartbeat"), "driver")
        robot.tick(.1)
        assert robot.grid.free(*robot.state.pose[:2])
        assert max(map(abs, robot.targets())) <= MAX_RPM+1e-10
        assert max(map(abs, robot.rpm)) <= MAX_RPM+1e-10
        if robot.mission.status != "running":
            break
    assert_idle(robot)
    assert robot.mission.last_result["status"] == "completed"
    assert robot.mission.last_result["progress"] == 100
    assert math.dist(robot.state.pose[:2], destination[:2]) < .035
    assert abs(wrap_angle(robot.state.pose[2]-destination[2])) < .035


def collision_events(robot):
    return [event for event in robot.events if "collision prevented" in event["message"]]


def block_autonomous(robot):
    navigate(robot,"start",goal=Goal(x=2,y=1))
    # Inject an obstacle at the current pose to exercise the runtime guard,
    # rather than the planner rejecting a goal before a mission exists.
    cx,cy=robot.grid.cell(robot.state.pose)
    robot.grid.data[cy*robot.grid.width+cx]=100
    robot.tick(.1)
    assert robot.mission.status == "blocked"
    assert robot.rpm == robot.targets() == [0,0]
    assert robot.owner is None
    assert robot.snapshot()["clearance"]["pose_clear"] is False
    assert "Autonomous navigation" in robot.mission.reason
    assert "Current pose is obstructed" in robot.mission.reason
    return cx,cy


def test_manual_collision_is_idle_and_warning_is_not_repeated():
    robot=RobotSimulator()
    for _ in range(200):
        command(robot,linear=.6)
        robot.tick(.1)
        if collision_events(robot):
            break
    assert_idle(robot)
    assert robot.grid.free(*robot.state.pose[:2])
    assert len(collision_events(robot)) == 1
    assert "Manual motion" in collision_events(robot)[0]["message"]
    stopped_pose, stopped_counts=robot.state.pose,list(robot.counts)
    for _ in range(30):
        command(robot,linear=.6)
        robot.tick(.1)
    assert robot.state.pose == stopped_pose
    assert robot.counts == stopped_counts
    assert len(collision_events(robot)) == 1
    assert_idle(robot)
    # Driving away ends the episode; a later encounter deserves another warning.
    for _ in range(15):
        command(robot,linear=-.18)
        robot.tick(.1)
    assert robot.collision_origin is None
    for _ in range(50):
        command(robot,linear=.18)
        robot.tick(.1)
        if len(collision_events(robot)) == 2:
            break
    assert len(collision_events(robot)) == 2
    assert_idle(robot)


@pytest.mark.parametrize("action",["stop","cancel"])
def test_autonomous_block_and_stop_or_cancel_clear_failure(action):
    robot=RobotSimulator()
    robot.mission.save("A",Goal(x=2,y=1))
    block_autonomous(robot)
    original_reason=robot.mission.reason
    for _ in range(30):
        robot.tick(.1)
    assert robot.mission.reason == original_reason
    assert len(collision_events(robot)) == 1
    if action == "stop":
        robot.command(ControlCommand(type="stop"),"observer")
    else:
        navigate(robot,"cancel")
    assert_idle(robot)
    assert robot.mission.last_result["status"] == "cancelled"
    assert "A" in robot.mission.waypoints
    robot.tick(.1)
    assert_idle(robot)
    assert len(collision_events(robot)) == 1


@pytest.mark.parametrize("status",["idle","ready","running","paused"])
def test_explicit_cancel_clears_live_mission_and_is_idempotent(status):
    robot=RobotSimulator()
    if status != "idle":
        navigate(robot,"plan" if status=="ready" else "start",goal=Goal(x=2,y=1))
    if status == "paused":
        navigate(robot,"pause")
    navigate(robot,"cancel")
    assert_idle(robot)
    event_count=robot.event_id
    navigate(robot,"cancel")
    robot.command(ControlCommand(type="stop"),"driver")
    assert_idle(robot)
    # navigate() acknowledges each command, but repeated STOP adds no warning.
    assert sum(event["level"]=="warning" for event in robot.events) <= 1
    assert robot.event_id <= event_count+1


def test_manual_takeover_clears_preview_and_blocked_mission():
    robot=RobotSimulator()
    navigate(robot,"plan",goal=Goal(x=2,y=1))
    command(robot,linear=.1)
    assert robot.mission.status == "idle"
    assert robot.mission.snapshot()["path"] == []
    robot.command(ControlCommand(type="release"),"driver")
    cx,cy=block_autonomous(robot)
    robot.grid.data[cy*robot.grid.width+cx]=0
    command(robot,linear=-.1)
    assert robot.mission.status == "idle"
    assert robot.mission.snapshot()["destination"] is None


def test_footprint_home_reported_pose_boundary_and_corner_clearance():
    grid=OccupancyGrid()
    assert grid.clearance == pytest.approx(math.hypot(CHASSIS_SIZE/2,CHASSIS_SIZE/2)+.025)
    assert grid.free(*HOME[:2])
    # Pose observed in the running dashboard before the audit (stale BLOCKED).
    assert grid.free(2.895674638014687,1.291714679138781)
    r=grid.clearance
    assert grid.free(.2+r+.001,1)
    assert not grid.free(.2+r-.001,1)
    # Wall starts at (3.2,.8). Test rounded clearance near its lower-left corner.
    near=3.2-r/math.sqrt(2), .8-r/math.sqrt(2)
    assert not grid.free(near[0]+.0001,near[1]+.0001)
    assert grid.free(near[0]-.0001,near[1]-.0001)
    robot=RobotSimulator()
    assert robot.snapshot()["clearance"] == {"pose_clear":True,"radius":r}
    data=[0]*1200
    data[5*40+5]=100
    with pytest.raises(ValueError,match="Home pose lacks"):
        RobotSimulator(grid=OccupancyGrid(data=data))


def test_swept_footprint_detects_a_grazing_corner_between_samples():
    data=[0]*400
    data[10*20+10]=100
    grid=OccupancyGrid(20,20,.2,data)
    d=(grid.clearance-.00001)/math.sqrt(2)
    closest=(2-d,2-d)
    tangent=(1/math.sqrt(2),-1/math.sqrt(2))
    start=tuple(closest[i]-.18*tangent[i] for i in range(2))
    end=tuple(closest[i]+.22*tangent[i] for i in range(2))
    assert grid.free(*start) and grid.free(*end)
    assert not grid.segment_free(start,end)


@pytest.mark.parametrize("linear,angular",[(.1,.3),(0,.8),(-.1,-.3)])
def test_independent_encoder_integration_and_raw_polarity_do_not_change_odometry(linear,angular):
    robot=RobotSimulator()
    reference=RobotSimulator(DriveConfig(encoder_polarity=(1,1)))
    # Above the ramp duration both targets are constant; integrate each wheel.
    for _ in range(10):
        for sim in (robot,reference):
            command(sim,linear=linear,angular=angular)
            sim.tick(.1)
    before=list(robot.counts)
    rpm=list(robot.rpm)
    assert rpm[0] != pytest.approx(rpm[1])
    for sim in (robot,reference):
        command(sim,linear=linear,angular=angular)
        sim.tick(.1)
    for i in range(2):
        assert robot.counts[i]-before[i] == pytest.approx(rpm[i]*ENCODER_CPR*.1/60)
    assert robot.counts == pytest.approx(reference.counts)
    assert robot.state.pose == pytest.approx(reference.state.pose)
    motors=robot.snapshot()["motors"]
    assert robot.drive.config.encoder_polarity == (1,-1)
    assert motors[0]["raw_encoder_count"] == motors[0]["encoder_count"]
    assert motors[1]["raw_encoder_count"] == -motors[1]["encoder_count"]


def test_exact_abc_sequence_visits_every_waypoint_and_returns_home():
    robot=RobotSimulator()
    goals={"A":(2,1,0),"B":(2,2,0),"C":(1,2,0)}
    for name,(x,y,yaw) in goals.items():
        robot.command(WaypointCommand(type="waypoint",name=name,goal=Goal(x=x,y=y,yaw=yaw)),"driver")
    navigate(robot,"sequence",waypoints=["A","B","C"])
    visited=[]
    for _ in range(2500):
        name=robot.mission.snapshot()["current_waypoint"]
        robot.command(ControlCommand(type="heartbeat"),"driver")
        robot.tick(.1)
        assert robot.grid.free(*robot.state.pose[:2])
        assert max(map(abs,robot.rpm)) <= MAX_RPM+1e-10
        if name and robot.mission.snapshot()["current_waypoint"] != name:
            assert math.dist(robot.state.pose[:2],goals[name][:2]) < .035
            assert abs(wrap_angle(robot.state.pose[2]-goals[name][2])) < .035
            visited.append(name)
        if robot.mission.status != "running":
            break
    assert visited == ["A","B","C"]
    assert_idle(robot)
    assert robot.mission.last_result["status"] == "completed"
    assert [g["name"] for g in robot.mission.last_result["goals"]] == ["A","B","C"]
    navigate(robot,"home")
    finish(robot,HOME)
    assert set(robot.mission.waypoints) == {"A","B","C"}


@pytest.mark.parametrize("destination",[(2,1,0),(2,2,0),(1,2,0)])
def test_each_waypoint_is_reachable_from_home_and_back(destination):
    robot=RobotSimulator()
    navigate(robot,"start",goal=Goal(x=destination[0],y=destination[1],yaw=destination[2]))
    finish(robot,destination)
    navigate(robot,"home")
    finish(robot,HOME)


def test_autonomous_swept_collision_retains_goal_until_stop_then_allows_new_mission():
    robot=RobotSimulator()
    navigate(robot,"start",goal=Goal(x=2,y=1))
    # Change a future path cell after planning, leaving the current pose clear.
    cx,cy=robot.grid.cell((1.8,1.0))
    robot.grid.data[cy*robot.grid.width+cx]=100
    assert robot.grid.free(*robot.state.pose[:2])
    for _ in range(200):
        robot.command(ControlCommand(type="heartbeat"),"driver")
        robot.tick(.1)
        if robot.mission.status == "blocked":
            break
    state=robot.snapshot()
    assert state["navigation"]["status"] == "blocked"
    assert state["navigation"]["destination"]["x"] == 2
    assert state["navigation"]["path"]
    assert state["clearance"]["pose_clear"] is True
    assert "Autonomous navigation collision prevented" in state["navigation"]["reason"]
    assert robot.targets() == robot.rpm == [0,0]
    assert len(collision_events(robot)) == 1
    robot.command(ControlCommand(type="stop"),"observer")
    assert_idle(robot)
    robot.grid.data[cy*robot.grid.width+cx]=0
    navigate(robot,"start",goal=Goal(x=2,y=1))
    finish(robot,(2,1,0))
