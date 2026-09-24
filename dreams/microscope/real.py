import os
import tempfile
import time
from collections import OrderedDict

import numpy as np
from PIL import Image
from pycromanager import Core

from .common import array_to_png_bytes, normalise_to_uint8
from .image_adapter import CurrentCameraImageAdapter


class RealMicroscope:
    """Wrap pycromanager Core for real microscope control."""

    def __init__(self):
        self.core = Core()
        self._image_counter = 0
        self._last_pixels: np.ndarray | None = None
        self._image_adapter = CurrentCameraImageAdapter()
        self.position = {"x": 0.0, "y": 0.0, "z": 0.0}

        loaded_devices = self._java_list_to_python(self.core.get_loaded_devices())
        self._focus_device = "SimFocus" if "SimCam" in loaded_devices else None

    def move_stage(self, x: float, y: float, z: float) -> dict:
        self.core.set_xy_position(x, y)
        if self._focus_device:
            self.core.set_position(self._focus_device, z)
        else:
            self.core.set_position(z)
        self.position = {"x": x, "y": y, "z": z}
        return self.position

    def get_stage_position(self) -> dict:
        z_position = (
            self.core.get_position(self._focus_device)
            if self._focus_device
            else self.core.get_position()
        )
        self.position = {
            "x": self.core.get_x_position(),
            "y": self.core.get_y_position(),
            "z": z_position,
        }
        return self.position

    def snap_image(self) -> dict:
        """Capture an image and save a normalized PNG preview."""
        self.core.snap_image()
        tagged = self.core.get_tagged_image()

        tags = OrderedDict(sorted(tagged.tags.items()))
        pixels = tagged.pix
        height = tags["Height"]
        width = tags["Width"]
        channel_count = pixels.shape[0] // (height * width)

        if channel_count > 1:
            pixels = pixels.reshape(height, width, channel_count)
        else:
            pixels = pixels.reshape(height, width)

        self._last_pixels = pixels
        self._image_counter += 1

        path = os.path.join(
            tempfile.gettempdir(),
            f"scope_real_{self._image_counter:04d}.png",
        )
        display_pixels = self._image_adapter.to_display_pixels(
            normalise_to_uint8(pixels)
        )
        Image.fromarray(display_pixels).save(path)

        return {
            "status": "ok",
            "filename": f"image_{self._image_counter:04d}.tif",
            "position": self.position,
            "image_path": path,
            "shape": (
                [height, width]
                if channel_count == 1
                else [height, width, channel_count]
            ),
            "dtype": str(tagged.pix.dtype),
        }

    def get_image_png(self) -> bytes:
        """Return the last captured image as raw PNG bytes."""
        if self._last_pixels is None:
            raise RuntimeError("No image captured yet — call snap_image() first.")
        display_pixels = self._image_adapter.to_display_pixels(
            normalise_to_uint8(self._last_pixels)
        )
        return array_to_png_bytes(display_pixels)

    def wait(self, seconds: float) -> dict:
        time.sleep(seconds)
        return {"status": "ok", "waited_seconds": seconds}

    @staticmethod
    def _java_list_to_python(value):
        return [value.get(index) for index in range(value.size())]
