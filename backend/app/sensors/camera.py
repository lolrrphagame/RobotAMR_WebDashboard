"""A metadata-only placeholder. Never opens a device or creates camera frames."""
from .contracts import SensorFrame


class PlaceholderCamera:
    def snapshot(self, now, include_data=True):
        frame = SensorFrame(sensor_type="camera", source="PLACEHOLDER", status="NOT_CONNECTED",
            frame_id="front_camera_optical", metadata={"width": None, "height": None,
                "encoding": None, "fps": None, "stream_url": None,
                "preview_kind": "static_ui_test_pattern", "frames_received": 0},
            interface={"connection_state": "DISABLED", "planned_topic": "/camera/image_raw",
                       "compressed_topic": "/camera/image_raw/compressed",
                       "message_types": ["sensor_msgs/Image", "sensor_msgs/CompressedImage"],
                       "note": "A future backend streaming adapter must supply frames and their metadata."})
        return frame.model_dump(exclude={"payload"} if not include_data else set())
