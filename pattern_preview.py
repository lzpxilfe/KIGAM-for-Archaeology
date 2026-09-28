"""Side-by-side map preview using private layer clones until the user applies."""
from qgis.core import QgsRectangle
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox, QComboBox,
    QDialogButtonBox, QPushButton,
)
from .pattern_utils import scale_patterns


class ComparisonCanvas(QgsMapCanvas):
    def wheelEvent(self, event):
        # Both panels keep the common scale selected above.
        event.ignore()


class PatternPreviewDialog(QDialog):
    def __init__(self, source_canvas, layers, multiplier=2.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle('면 패턴 비교')
        self.resize(1000, 650)
        self._originals = list(layers)
        self._clones = {layer.id(): layer.clone() for layer in layers}
        self._initial_extent = QgsRectangle(source_canvas.extent())
        visible = source_canvas.layers()
        self._before_layers = [layer for layer in layers if layer not in visible] + visible
        self._after_layers = [self._clones.get(layer.id(), layer) for layer in self._before_layers]
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('왼쪽은 현재 스타일, 오른쪽은 변경 미리보기입니다. 적용을 눌러야 원본 레이어가 바뀝니다.'))
        controls = QHBoxLayout()
        controls.addWidget(QLabel('패턴 확대'))
        self.multiplier_spin = QDoubleSpinBox()
        self.multiplier_spin.setRange(0.5, 6)
        self.multiplier_spin.setSingleStep(0.5)
        self.multiplier_spin.setValue(multiplier)
        self.multiplier_spin.setSuffix(' 배')
        controls.addWidget(self.multiplier_spin)
        controls.addWidget(QLabel('비교 축척'))
        self.scale_combo = QComboBox()
        for scale in (10000, 25000, 50000, 100000):
            self.scale_combo.addItem(f'1:{scale:,}', scale)
        self.scale_combo.setCurrentIndex(1)
        controls.addWidget(self.scale_combo)
        reset = QPushButton('원래 크기 (1배)')
        reset.clicked.connect(lambda: self.multiplier_spin.setValue(1))
        controls.addWidget(reset)
        controls.addStretch()
        layout.addLayout(controls)
        panels = QHBoxLayout()
        self.before_canvas, self.after_canvas = ComparisonCanvas(self), ComparisonCanvas(self)
        for label, canvas, stack in (
                ('현재 스타일', self.before_canvas, self._before_layers),
                ('변경 미리보기', self.after_canvas, self._after_layers)):
            panel = QVBoxLayout()
            panel.addWidget(QLabel(label))
            canvas.setMinimumSize(320, 320)
            canvas.setCanvasColor(source_canvas.canvasColor())
            canvas.setDestinationCrs(source_canvas.mapSettings().destinationCrs())
            canvas.setLayers(stack)
            panel.addWidget(canvas)
            panels.addLayout(panel)
        layout.addLayout(panels)
        self.status = QLabel()
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('원본 레이어에 적용')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.multiplier_spin.valueChanged.connect(self.update_patterns)
        self.scale_combo.currentIndexChanged.connect(self.update_extent)
        self.finished.connect(self.stop_rendering)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.initialize_preview)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'before_canvas'):
            QTimer.singleShot(0, self.update_extent)

    def initialize_preview(self):
        if self.isVisible():
            self.update_patterns()
            self.update_extent()

    def update_patterns(self):
        self.after_canvas.stopRendering()
        changed = skipped = 0
        for clone in self._clones.values():
            report = scale_patterns(clone, self.multiplier_spin.value())
            changed += report['changed']
            skipped += report['skipped']
        self.status.setText(f'면 패턴 {changed}개 변경 · 데이터 정의/크기 확인 필요 {skipped}개')
        self.after_canvas.refresh()

    def update_extent(self):
        for canvas in (self.before_canvas, self.after_canvas):
            canvas.setExtent(self._initial_extent)
            canvas.zoomScale(self.scale_combo.currentData())
            canvas.refresh()

    def stop_rendering(self, *_):
        for canvas in (self.before_canvas, self.after_canvas):
            canvas.setRenderFlag(False)
            canvas.stopRendering()
            canvas.setLayers([])

    def selected_multiplier(self):
        return self.multiplier_spin.value()
