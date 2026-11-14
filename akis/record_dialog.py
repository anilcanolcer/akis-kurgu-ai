"""Record from the camera, the screen or the microphone straight into the project (CapCut-style "Kayıt").

The source is a camera (with a microphone, if one is chosen), a screen (with a microphone if chosen) or the
microphone alone (a voiceover). Cameras and the microphone are recorded by Qt Multimedia; screens by the
bundled ffmpeg (akis.screen_record), since Qt's screen capture is not available in this build. Files go to
the user's Videos folder, "Akış Kurgu kayıtları" (MP4, or M4A for sound only); the caller reads `path` and
`kind` ('video' or 'audio') after exec() and puts the file in the project. Nothing leaves the computer.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QStackedLayout,
                               QVBoxLayout, QWidget)

from akis import i18n, theme
from akis.screen_record import ScreenRecorder, audio_devices, screen_area

FOLDER_NAME = 'Akış Kurgu kayıtları'
CAMERA, SCREEN, MIC_ONLY = 'camera', 'screen', 'audio'
STYLE = """
QLabel#recTime { font-family: 'Cascadia Mono'; font-size: 22px; font-weight: 700; color: $text; }
QLabel#recDot { color: $cut; font-size: 18px; }
QLabel#recNote { color: $muted; }
QFrame#recStage, QWidget#recStage { background: $video_bg; border-radius: 10px; }
QLabel#recPlaceholder { color: $video_text; }
QPushButton#recStart { background: $cut; color: white; font-weight: 700; padding: 10px 22px; text-align: center; }
QPushButton#recStop { background: $raised; border: 1px solid $border_strong; font-weight: 700; padding: 10px 22px; text-align: center; }
"""


def default_folder() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation) or str(Path.home() / 'Videos')
    return Path(base) / FOLDER_NAME


def file_name(kind: str, when: datetime | None = None) -> str:
    stamp = (when or datetime.now()).strftime('%Y%m%d-%H%M%S')
    return f'kayit-{stamp}.{"m4a" if kind == "audio" else "mp4"}'


def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f'{seconds // 60:02d}:{seconds % 60:02d}'


class RecordDialog(QDialog):
    """`path` (the recorded file) and `kind` ('video' or 'audio') after exec() returns Accepted."""

    def __init__(self, parent=None, language='tr', folder=None, devices=None, executable='ffmpeg'):
        super().__init__(parent)
        from PySide6 import QtMultimedia as M
        self.M = M
        self.language = language
        self.folder = Path(folder) if folder else default_folder()
        self.devices = devices or M.QMediaDevices
        self.path, self.kind = None, None
        self._started = None
        self.executable = executable
        self.screen_recorder = ScreenRecorder(executable)
        self._dshow = None          # microphone names ffmpeg sees, read once when a screen is recorded
        t = self.tr_
        self.setWindowTitle(t('Kayıt'))
        self.resize(760, 600)
        self.setStyleSheet(theme.css(STYLE))

        self.session = M.QMediaCaptureSession(self)
        self.recorder = M.QMediaRecorder(self)
        self.session.setRecorder(self.recorder)
        self.camera = None
        self.screen_capture = None
        self.audio_input = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        note = QLabel(t('Kameradan, ekrandan ya da yalnız mikrofondan kayıt alın; kayıt bitince projeye eklenir. '
                        'Kayıt bilgisayarınızda kalır.'))
        note.setObjectName('recNote')
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        self.source = QComboBox()
        for camera in self.devices.videoInputs():
            self.source.addItem(t('Kamera: {name}').format(name=camera.description()), (CAMERA, camera))
        for screen in self._screens():
            self.source.addItem(t('Ekran: {name}').format(name=screen.name()), (SCREEN, screen))
        self.source.addItem(t('Yalnız ses (mikrofon)'), (MIC_ONLY, None))
        self.microphone = QComboBox()
        self.microphone.addItem(t('Mikrofon yok'), None)
        for device in self.devices.audioInputs():
            self.microphone.addItem(device.description(), device)
        if self.microphone.count() > 1:
            default = self.devices.defaultAudioInput()
            index = next((i for i in range(1, self.microphone.count())
                          if self.microphone.itemData(i).id() == default.id()), 1)
            self.microphone.setCurrentIndex(index)
        form.addRow(t('Kaynak'), self.source)
        form.addRow(t('Mikrofon'), self.microphone)
        layout.addLayout(form)

        stage = QWidget()
        stage.setObjectName('recStage')
        self.stage = QStackedLayout(stage)
        from PySide6.QtMultimediaWidgets import QVideoWidget
        self.preview = QVideoWidget()
        self.placeholder = QLabel()
        self.placeholder.setObjectName('recPlaceholder')
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.stage.addWidget(self.preview)
        self.stage.addWidget(self.placeholder)
        layout.addWidget(stage, 1)
        self.session.setVideoOutput(self.preview)

        row = QHBoxLayout()
        self.dot = QLabel('●')
        self.dot.setObjectName('recDot')
        self.dot.hide()
        self.time = QLabel('00:00')
        self.time.setObjectName('recTime')
        self.status = QLabel()
        self.status.setObjectName('recNote')
        self.status.setWordWrap(True)
        row.addWidget(self.dot)
        row.addWidget(self.time)
        row.addWidget(self.status, 1)
        self.start_button = QPushButton(t('● Kaydı başlat'))
        self.start_button.setObjectName('recStart')
        self.stop_button = QPushButton(t('■ Durdur ve ekle'))
        self.stop_button.setObjectName('recStop')
        self.stop_button.setEnabled(False)
        self.close_button = QPushButton(t('Kapat'))
        for button in (self.start_button, self.stop_button, self.close_button):
            button.setAutoDefault(False)
            row.addWidget(button)
        layout.addLayout(row)

        self.ticker = QTimer(self)
        self.ticker.setInterval(250)
        self.ticker.timeout.connect(self._tick)
        self.source.currentIndexChanged.connect(self._use_source)
        self.microphone.currentIndexChanged.connect(self._use_microphone)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        self.close_button.clicked.connect(self.reject)
        self.recorder.recorderStateChanged.connect(self._state_changed)
        self.recorder.errorOccurred.connect(self._failed)
        self._use_microphone()
        self._use_source()

    def tr_(self, text):
        return i18n.translate(text, self.language)

    @staticmethod
    def _screens():
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.screens()

    def current_source(self):
        return self.source.currentData() or (MIC_ONLY, None)

    def _use_source(self):
        """Point the session at the chosen camera or screen (none for sound only) and show its preview."""
        M = self.M
        kind, device = self.current_source()
        if self.camera is not None:
            self.camera.stop()
            self.session.setCamera(None)
            self.camera.deleteLater()
            self.camera = None
        if self.screen_capture is not None:
            self.screen_capture.stop()
            self.session.setScreenCapture(None)
            self.screen_capture.deleteLater()
            self.screen_capture = None
        if kind == CAMERA:
            self.camera = M.QCamera(device, self)
            self.session.setCamera(self.camera)
            self.camera.start()
            self.stage.setCurrentWidget(self.preview)
        elif kind == SCREEN:
            x, y, width, height = screen_area(device)
            self.placeholder.setText(self.tr_('“{name}” ekranı kaydedilecek ({width}×{height}). Kaydı başlattıktan sonra '
                                              'bu pencereyi küçültüp ekranda göstermek istediğinizi yapabilirsiniz.').format(
                                                  name=device.name(), width=width, height=height))
            self.stage.setCurrentWidget(self.placeholder)
        else:
            self.placeholder.setText(self.tr_('Yalnız ses kaydedilir. Kayıt, oynatma çizgisinin olduğu yere '
                                              'seslendirme olarak eklenir.'))
            self.stage.setCurrentWidget(self.placeholder)
        self._update_ready()

    def _use_microphone(self):
        device = self.microphone.currentData()
        if device is None:
            self.session.setAudioInput(None)
            self.audio_input = None
        else:
            self.audio_input = self.M.QAudioInput(device, self)
            self.session.setAudioInput(self.audio_input)
        self._update_ready()

    def _update_ready(self):
        kind, _ = self.current_source()
        ready = kind != MIC_ONLY or self.microphone.currentData() is not None
        recording = (self.recorder.recorderState() == self.M.QMediaRecorder.RecorderState.RecordingState
                     or self.screen_recorder.recording)
        self.start_button.setEnabled(ready and not recording)
        if recording:
            self.status.setText(self.tr_('Kaydediliyor…'))
        elif not ready:
            self.status.setText(self.tr_('Yalnız ses kaydı için bir mikrofon seçin; bu bilgisayarda mikrofon görünmüyor.')
                                if self.microphone.count() == 1 else self.tr_('Yalnız ses kaydı için bir mikrofon seçin.'))
        elif not recording:
            self.status.setText('')

    def _dshow_name(self):
        """The chosen microphone as ffmpeg's DirectShow knows it (its name there), or None."""
        device = self.microphone.currentData()
        if device is None:
            return None
        if self._dshow is None:
            self._dshow = audio_devices(self.executable)
        wanted = device.description()
        return next((name for name in self._dshow if name == wanted), None) or \
            next((name for name in self._dshow if wanted in name or name in wanted), None)

    def start(self):
        M = self.M
        kind, device = self.current_source()
        self.kind = 'audio' if kind == MIC_ONLY else 'video'
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self.folder / file_name(self.kind)
        if kind == SCREEN:
            try:
                self.screen_recorder.start(screen_area(device), target, self._dshow_name())
            except (OSError, RuntimeError) as exc:
                self._failed(None, str(exc))
                return
            self.path = None
            self._state_changed(M.QMediaRecorder.RecorderState.RecordingState)
            return
        fmt = M.QMediaFormat()
        if self.kind == 'audio':
            fmt.setFileFormat(M.QMediaFormat.FileFormat.Mpeg4Audio)
            fmt.setAudioCodec(M.QMediaFormat.AudioCodec.AAC)
        else:
            fmt.setFileFormat(M.QMediaFormat.FileFormat.MPEG4)
            fmt.setVideoCodec(M.QMediaFormat.VideoCodec.H264)
            if self.audio_input is not None:
                fmt.setAudioCodec(M.QMediaFormat.AudioCodec.AAC)
        self.recorder.setMediaFormat(fmt)
        self.recorder.setQuality(M.QMediaRecorder.Quality.HighQuality)
        self.recorder.setOutputLocation(QUrl.fromLocalFile(str(target)))
        self.path = None
        self.recorder.record()

    def stop(self):
        if self.screen_recorder.recording:
            self.status.setText(self.tr_('Kayıt kapatılıyor…'))
            try:
                self.path = self.screen_recorder.stop()
            except RuntimeError as exc:
                self._started = None
                self._failed(None, str(exc))
                self._state_changed(self.M.QMediaRecorder.RecorderState.StoppedState)
                return
            self._started = None
            self._state_changed(self.M.QMediaRecorder.RecorderState.StoppedState)
            self.accept()
            return
        self.recorder.stop()

    def _state_changed(self, state):
        recording = state == self.M.QMediaRecorder.RecorderState.RecordingState
        self.stop_button.setEnabled(recording)
        self.source.setEnabled(not recording)
        self.microphone.setEnabled(not recording)
        self.close_button.setEnabled(not recording)
        self.dot.setVisible(recording)
        if recording:
            self._started = time.monotonic()
            self.ticker.start()
            self.status.setText(self.tr_('Kaydediliyor…'))
        else:
            self.ticker.stop()
            if state == self.M.QMediaRecorder.RecorderState.StoppedState and self._started is not None:
                self._started = None
                location = self.recorder.actualLocation().toLocalFile()
                if location and Path(location).is_file() and Path(location).stat().st_size > 0:
                    self.path = location
                    self.accept()
                    return
                self.status.setText(self.tr_('Kayıt dosyası oluşmadı.'))
        self._update_ready()

    def _tick(self):
        if self._started is not None:
            self.time.setText(clock(time.monotonic() - self._started))
        problem = self.screen_recorder.failed() if self.kind == 'video' else ''
        if problem:                       # ffmpeg stopped by itself (a busy or missing device)
            self._started = None
            self._failed(None, problem)
            self._state_changed(self.M.QMediaRecorder.RecorderState.StoppedState)

    def _failed(self, error, message):
        self.ticker.stop()
        self._started = None
        self.status.setText(self.tr_('Kayıt yapılamadı: {error}').format(error=message or str(error)))
        self._update_ready()

    def done(self, result):
        """Stop the devices when the dialog closes, however it closes."""
        if self.screen_recorder.recording:
            try:
                self.screen_recorder.stop()
            except RuntimeError:
                pass
        if self.recorder.recorderState() != self.M.QMediaRecorder.RecorderState.StoppedState:
            self.recorder.stop()
        for device in (self.camera, self.screen_capture):
            if device is not None:
                device.stop()
        super().done(result)
