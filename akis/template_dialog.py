from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QLabel, QComboBox, QPushButton
from akis.template_service import TEMPLATES, STYLES, TEMPOS

class TemplateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Şablonlar')
        self.resize(600, 540)
        layout = QVBoxLayout(self)
        intro = QLabel('Seçtiğiniz şablon, mevcut projeye adlandırılmış izleri, en-boy oranını, renk stilini ve tempoyu ekler. '
                       'Medyanızı ilgili izlere kendiniz yerleştirirsiniz.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.list = QListWidget()
        self.list.addItems([f'{t.name}  ·  {t.ratio}  ·  ~{t.seconds} sn' for t in TEMPLATES])
        layout.addWidget(self.list)
        self.details = QLabel(); self.details.setWordWrap(True); layout.addWidget(self.details)
        self.style = QComboBox(); self.style.addItems(STYLES)
        self.tempo = QComboBox(); self.tempo.addItems(TEMPOS)
        layout.addWidget(QLabel('Renk stili')); layout.addWidget(self.style)
        layout.addWidget(QLabel('Tempo (tüm proje hızı)')); layout.addWidget(self.tempo)
        row = QHBoxLayout()
        apply = QPushButton('Mevcut projeye uygula'); apply.clicked.connect(self.accept)
        row.addWidget(apply); layout.addLayout(row)
        self.list.currentRowChanged.connect(self.changed)
        self.list.setCurrentRow(0)
    def changed(self, index):
        if index < 0: return
        t = TEMPLATES[index]
        self.details.setText('İzler: ' + ' / '.join(n for _, n in t.tracks) + '\nDüzenlenebilir başlık: ' + t.title + ' (3 sn, varsayılan metin stili)')
        self.style.setCurrentText(t.style); self.tempo.setCurrentText(t.tempo)
    def selection(self):
        return TEMPLATES[self.list.currentRow()], self.style.currentText(), self.tempo.currentText()
