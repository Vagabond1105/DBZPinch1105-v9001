"""Qt controls generated from the dataclass metadata in params.py."""

import math

from PyQt5 import QtCore, QtWidgets

SLIDER_STEPS = 1000


class FloatControl(QtWidgets.QWidget):
    """Slider + spin box. Log-scaled params with lo == 0 reserve the leftmost slider position for 0."""

    def __init__(self, meta, value, on_change):
        super().__init__()
        self.lo, self.hi = float(meta["lo"]), float(meta["hi"])
        self.log = bool(meta["log"])
        self.on_change = on_change
        self._log_lo = self.lo if self.lo > 0 else self.hi * 1e-3

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, SLIDER_STEPS)
        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setRange(self.lo, self.hi)
        span = self.hi - self.lo
        decimals = max(2, int(math.ceil(-math.log10(self._log_lo if self.log else span / 1000))) + 1)
        self.spin.setDecimals(min(decimals, 6))
        self.spin.setSingleStep(span / 100.0)
        self.spin.setKeyboardTracking(False)
        self.spin.setFixedWidth(92)

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)

        self.set_value(value)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)

    def _to_pos(self, v):
        if self.log:
            if v <= 0.0 or v < self._log_lo * 0.999:
                return 0
            f = math.log(v / self._log_lo) / math.log(self.hi / self._log_lo)
            return int(round(1 + f * (SLIDER_STEPS - 1)))
        return int(round((v - self.lo) / (self.hi - self.lo) * SLIDER_STEPS))

    def _from_pos(self, pos):
        if self.log:
            if pos == 0:
                return self.lo
            f = (pos - 1) / (SLIDER_STEPS - 1)
            return self._log_lo * (self.hi / self._log_lo) ** f
        return self.lo + pos / SLIDER_STEPS * (self.hi - self.lo)

    def _from_slider(self, pos):
        v = self._from_pos(pos)
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self.on_change(v)

    def _from_spin(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(self._to_pos(v))
        self.slider.blockSignals(False)
        self.on_change(v)

    def set_value(self, v):
        for w in (self.slider, self.spin):
            w.blockSignals(True)
        self.spin.setValue(v)
        self.slider.setValue(self._to_pos(v))
        for w in (self.slider, self.spin):
            w.blockSignals(False)


class IntControl(QtWidgets.QSpinBox):
    def __init__(self, meta, value, on_change):
        super().__init__()
        self.setRange(int(meta["lo"]), int(meta["hi"]))
        self.setSingleStep(int(meta["step"] or 1))
        self.setKeyboardTracking(False)
        self.setValue(int(value))
        self.valueChanged.connect(lambda v: on_change(int(v)))

    def set_value(self, v):
        self.blockSignals(True)
        self.setValue(int(v))
        self.blockSignals(False)


class BoolControl(QtWidgets.QCheckBox):
    def __init__(self, meta, value, on_change):
        super().__init__()
        self.setChecked(bool(value))
        self.toggled.connect(lambda v: on_change(bool(v)))

    def set_value(self, v):
        self.blockSignals(True)
        self.setChecked(bool(v))
        self.blockSignals(False)


class ChoiceControl(QtWidgets.QComboBox):
    def __init__(self, meta, value, on_change):
        super().__init__()
        self.addItems(meta["choices"])
        self.setCurrentText(value)
        self.currentTextChanged.connect(on_change)

    def set_value(self, v):
        self.blockSignals(True)
        self.setCurrentText(v)
        self.blockSignals(False)


def make_control(default, meta, value, on_change):
    if meta.get("choices"):
        return ChoiceControl(meta, value, on_change)
    if isinstance(default, bool):
        return BoolControl(meta, value, on_change)
    if isinstance(default, int):
        return IntControl(meta, value, on_change)
    return FloatControl(meta, value, on_change)


def build_form(params_obj, describe_list, on_change):
    """
    Returns (widget, controls dict). on_change(name, value) is called after
    the dataclass attribute has been updated.
    """
    box = QtWidgets.QWidget()
    form = QtWidgets.QFormLayout(box)
    form.setLabelAlignment(QtCore.Qt.AlignLeft)
    form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
    form.setContentsMargins(6, 6, 6, 6)
    controls = {}
    for name, default, meta in describe_list:
        def cb(v, name=name):
            setattr(params_obj, name, v)
            on_change(name, v)
        ctrl = make_control(default, meta, getattr(params_obj, name), cb)
        label = QtWidgets.QLabel(meta["label"])
        for w in (label, ctrl):
            w.setToolTip(meta["help"])
        form.addRow(label, ctrl)
        controls[name] = ctrl
    return box, controls
