"""
3D view: GPU ray-cast volume of a chosen field, passive tracers, and the
domain outline. Everything lives in physical coordinates (domain width 1,
z centred on 0).
"""

import numpy as np
from matplotlib import colormaps as mpl_colormaps
from vispy import scene
from vispy.color import Colormap
from vispy.visuals.transforms import MatrixTransform, STTransform

RENDER_MODES = {
    "Glow (additive)": dict(method="additive"),
    "Translucent": dict(method="translucent"),
    "Max intensity": dict(method="mip"),
    "Isosurface": dict(method="iso"),
    "Slice x-z (y = 0)": dict(slice="xz"),
    "Slice x-y (z = 0)": dict(slice="xy"),
}

COLORMAPS = ("inferno", "plasma", "magma", "viridis", "cividis", "turbo", "coolwarm")


def make_colormap(name, method):
    """
    matplotlib colormap -> vispy Colormap. Translucent rendering gets an
    alpha ramp; additive rendering fades the low end to black, otherwise
    the faint background accumulates along every ray into a haze.
    """
    ramp = np.linspace(0.0, 1.0, 64)
    cols = mpl_colormaps[name](ramp)
    if method == "translucent":
        cols[:, 3] = ramp ** 1.6
    elif method == "additive":
        cols[:, :3] *= (ramp ** 2)[:, None]
    return Colormap(cols)


class PinchView:

    def __init__(self, parent=None):
        self.canvas = scene.SceneCanvas(keys=None, bgcolor="#0b0d12", parent=parent, show=False)
        self.view = self.canvas.central_widget.add_view()
        self.view.camera = scene.cameras.TurntableCamera(
            fov=40, elevation=18, azimuth=-60, distance=3.2, up="+z")

        self.volume = None
        self._vol_shape = None
        self.image = None
        self._mode = "Glow (additive)"
        self._cmap_name = "inferno"
        self._threshold = 0.5
        self.markers = scene.visuals.Markers(parent=self.view.scene, scaling="fixed")
        self.markers.set_gl_state("translucent", depth_test=False)
        self.markers.order = 10
        self.outline = None
        self.lo = np.zeros(3)
        self.hi = np.ones(3)
        self.dx = 1.0

        self.canvas.events.key_press.connect(self._on_key)

    # =====================================================
    # geometry
    # =====================================================

    def set_geometry(self, lo, hi, dx, shape):
        self.lo = np.asarray(lo, dtype=float)
        self.hi = np.asarray(hi, dtype=float)
        self.dx = float(dx)
        if self.outline is not None:
            self.outline.parent = None
        (x0, y0, z0), (x1, y1, z1) = self.lo, self.hi
        corners = np.array([[x, y, z] for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)], dtype=np.float32)
        edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
        seg = np.array([corners[e] for pair in edges for e in pair], dtype=np.float32)
        self.outline = scene.visuals.Line(pos=seg, connect="segments", color=(0.45, 0.5, 0.6, 0.6),
                                          parent=self.view.scene)
        if self.volume is not None and self._vol_shape != tuple(shape):
            self.volume.parent = None
            self.volume = None
        self.view.camera.center = tuple(0.5 * (self.lo + self.hi))
        self.view.camera.distance = 1.6 * float(np.max(self.hi - self.lo)) + 1.0

    def reset_camera(self):
        cam = self.view.camera
        cam.elevation, cam.azimuth = 18.0, -60.0
        cam.center = tuple(0.5 * (self.lo + self.hi))
        cam.distance = 1.6 * float(np.max(self.hi - self.lo)) + 1.0

    # =====================================================
    # volume
    # =====================================================

    @property
    def is_slice(self):
        return "slice" in RENDER_MODES[self._mode]

    def _make_volume(self, data_zyx, clim):
        if self.volume is not None:
            self.volume.parent = None
        method = RENDER_MODES[self._mode]["method"]
        self.volume = scene.visuals.Volume(
            data_zyx, clim=clim, method=method,
            cmap=make_colormap(self._cmap_name, method),
            threshold=self._threshold, relative_step_size=0.6,
            interpolation="linear", parent=self.view.scene)
        self.volume.transform = STTransform(scale=(self.dx,) * 3, translate=tuple(self.lo + 0.5 * self.dx))
        self.volume.order = 0
        self._vol_shape = data_zyx.shape[::-1]

    def _show_slice(self, data_xyz, clim):
        """Mid-plane slice drawn as a flat image in its true 3D position."""
        nx, ny, nz = data_xyz.shape
        kind = RENDER_MODES[self._mode]["slice"]
        if kind == "xz":   # y = 0 lies between the two middle cells for even ny
            img = 0.5 * (data_xyz[:, (ny - 1) // 2, :] + data_xyz[:, ny // 2, :])
        else:
            img = 0.5 * (data_xyz[:, :, (nz - 1) // 2] + data_xyz[:, :, nz // 2])
        img = np.ascontiguousarray(img.T, dtype=np.float32)   # rows = 2nd axis, cols = x
        if self.image is None:
            self.image = scene.visuals.Image(img, cmap=make_colormap(self._cmap_name, "mip"),
                                             clim=clim, interpolation="bilinear", parent=self.view.scene)
            self.image.set_gl_state("translucent", depth_test=False, cull_face=False)
            self.image.order = 0
        else:
            self.image.set_data(img)
            self.image.clim = clim
        # image pixels span [i, i+1] in local coordinates
        tr = MatrixTransform()
        tr.scale((self.dx, self.dx, 1.0))
        if kind == "xz":
            tr.rotate(90, (1, 0, 0))                    # local y -> physical z
            tr.translate((self.lo[0], 0.0, self.lo[2]))
        else:
            tr.translate((self.lo[0], self.lo[1], 0.0))
        self.image.transform = tr

    def set_style(self, mode=None, cmap=None, threshold=None):
        rebuild = False
        if mode is not None and mode != self._mode:
            self._mode = mode
            rebuild = True
        if cmap is not None and cmap != self._cmap_name:
            self._cmap_name = cmap
            rebuild = True
        if threshold is not None:
            self._threshold = threshold
            if self.volume is not None:
                self.volume.threshold = threshold
        if rebuild:
            for vis in (self.volume, self.image):
                if vis is not None:
                    vis.parent = None
            self.volume = None
            self.image = None

    def set_field(self, data_xyz, clim):
        clim = (float(clim[0]), float(clim[1]) if clim[1] > clim[0] else float(clim[0]) + 1e-6)
        if self.is_slice:
            self._show_slice(data_xyz, clim)
            return
        data_zyx = np.ascontiguousarray(data_xyz.T, dtype=np.float32)
        if self.volume is None or self._vol_shape != data_xyz.shape:
            self._make_volume(data_zyx, clim)
        else:
            self.volume.set_data(data_zyx, clim=clim, copy=False)

    # =====================================================
    # tracers
    # =====================================================

    def set_tracers(self, pos, colors, size, visible):
        self.markers.visible = bool(visible) and pos.shape[0] > 0
        if not self.markers.visible:
            return
        self.markers.set_data(pos.astype(np.float32), face_color=colors, edge_width=0, size=size)

    # =====================================================
    # keyboard orbit / zoom (mouse orbit/zoom/pan is built in)
    # =====================================================

    def _on_key(self, event):
        if event.key is None:
            return
        cam = self.view.camera
        name = event.key.name
        if name in ("Left", "A"):
            cam.azimuth -= 4
        elif name in ("Right", "D"):
            cam.azimuth += 4
        elif name in ("Up", "W"):
            cam.elevation = min(cam.elevation + 4, 90)
        elif name in ("Down", "S"):
            cam.elevation = max(cam.elevation - 4, -90)
        elif name in ("+", "="):
            cam.distance *= 0.92
        elif name in ("-", "_"):
            cam.distance /= 0.92
        elif name == "R":
            self.reset_camera()
        else:
            return
        self.canvas.update()
