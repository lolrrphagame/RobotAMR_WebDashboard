"""Static ROS-style occupancy data and conservative footprint-aware 4-connected A*."""
import heapq
import math


class OccupancyGrid:
    def __init__(self, width=40, height=30, resolution=0.2, data=None):
        self.width, self.height, self.resolution = width, height, resolution
        self.origin = (0.0, 0.0)
        self.frame_id = "map"
        # Circumscribed 250 mm square + 25 mm margin, independent of heading.
        self.clearance = math.sqrt(2) * 0.125 + 0.025
        self.data = list(data) if data is not None else [0] * (width * height)
        if len(self.data) != width * height:
            raise ValueError("Invalid occupancy grid size")
        if data is None:
            for y in range(height):
                for x in range(width):
                    if x in (0, width - 1) or y in (0, height - 1):
                        self.data[y * width + x] = 100
            # Warehouse shelving, central wall with a passage, and a lower island.
            for x0, y0, x1, y1 in [(16, 4, 18, 19), (25, 18, 34, 21), (8, 20, 13, 24), (26, 6, 30, 11)]:
                for y in range(y0, min(y1, height - 1)):
                    for x in range(x0, min(x1, width - 1)):
                        self.data[y * width + x] = 100

    def cell(self, point):
        return tuple(math.floor((point[i] - self.origin[i]) / self.resolution) for i in range(2))

    def center(self, cell):
        return tuple(self.origin[i] + (cell[i] + 0.5) * self.resolution for i in range(2))

    def free(self, x, y):
        """Disk-vs-cell AABB collision, treating unknown/outside cells as occupied."""
        r, s = self.clearance, self.resolution
        ox, oy = self.origin
        if x - r < ox or y - r < oy or x + r >= ox + self.width * s or y + r >= oy + self.height * s:
            return False
        for cy in range(math.floor((y - r - oy) / s), math.floor((y + r - oy) / s) + 1):
            for cx in range(math.floor((x - r - ox) / s), math.floor((x + r - ox) / s) + 1):
                if self.data[cy * self.width + cx] != 0:
                    dx = max(ox + cx * s - x, 0, x - (ox + (cx + 1) * s))
                    dy = max(oy + cy * s - y, 0, y - (oy + (cy + 1) * s))
                    if dx * dx + dy * dy <= r * r:
                        return False
        return True

    def segment_free(self, start, end):
        n = max(1, math.ceil(math.dist(start[:2], end[:2]) / (self.resolution / 5)))
        return all(self.free(start[0] + (end[0] - start[0]) * i / n,
                             start[1] + (end[1] - start[1]) * i / n) for i in range(n + 1))

    def snapshot(self):
        return {"id": "warehouse-v1", "frame_id": self.frame_id, "width": self.width,
                "height": self.height, "resolution": self.resolution,
                "origin": {"x": self.origin[0], "y": self.origin[1], "yaw": 0},
                "data": self.data, "clearance_radius": self.clearance}


def plan_path(grid: OccupancyGrid, start, goal):
    if not grid.free(*start[:2]) or not grid.free(*goal[:2]):
        raise ValueError("Destination or robot position has insufficient obstacle clearance")
    source, target = grid.cell(start), grid.cell(goal)
    frontier = [(0, source)]
    previous, cost = {source: None}, {source: 0}
    while frontier:
        _, current = heapq.heappop(frontier)
        if current == target:
            cells = []
            while current is not None:
                cells.append(current)
                current = previous[current]
            path = [tuple(start[:2])] + [grid.center(c) for c in reversed(cells)] + [tuple(goal[:2])]
            if not all(grid.segment_free(a, b) for a, b in zip(path, path[1:])):
                raise ValueError("No safe connection from pose to grid path")
            return path
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            neighbor = current[0] + dx, current[1] + dy
            if not grid.segment_free(grid.center(current), grid.center(neighbor)):
                continue
            next_cost = cost[current] + 1
            if neighbor not in cost or next_cost < cost[neighbor]:
                cost[neighbor] = next_cost
                previous[neighbor] = current
                heuristic = abs(neighbor[0] - target[0]) + abs(neighbor[1] - target[1])
                heapq.heappush(frontier, (next_cost + heuristic, neighbor))
    raise ValueError("No collision-free path to destination")
