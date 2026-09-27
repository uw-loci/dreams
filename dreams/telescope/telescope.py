import numpy as np


class Telescope:

    def __init__(self):
        self.position = {"x": 0, "y": 0, "z": 0}

    def move_stage(self, x: float, y: float, z: float) -> dict:
        self.position = {"x": x, "y": y, "z": z}
        return self.position

    def get_stage_position(self) -> dict:
        return self.position

    def get_image_png(self) -> np.ndarray:
        return np.random.randint(0, 255, [256, 256])
