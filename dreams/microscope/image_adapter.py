import numpy as np


class CurrentCameraImageAdapter:
    """Convert frames from the currently configured camera for PNG output."""

    def to_display_pixels(self, pixels: np.ndarray) -> np.ndarray:
        display_pixels = pixels.astype(np.uint8)
        if display_pixels.ndim == 3 and display_pixels.shape[2] == 4:
            # This camera supplies an unused fourth byte set to zero. Treating
            # it as PNG alpha makes valid RGB data fully transparent.
            return display_pixels[:, :, :3]
        return display_pixels
