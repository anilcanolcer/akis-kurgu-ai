"""Look at an AI edit plan before it is applied, and keep only the parts you want.

The plan is split into the parts a person thinks in (the new cut, its transitions, captions, on-screen
texts, marks, colour, speed, aspect, sound, the publish texts, removals). Each is a checkbox, all ticked;
the plan applied afterwards holds only the ticked parts. Self-contained: the host calls review(plan).
"""
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QScrollArea, QVBoxLayout, QWidget

from akis import i18n

TITLE = 'AI planını incele'


def parts(plan, say=str):
    """[(key, label)] for what the plan would do, in the order it is applied. `say` translates."""
    found = []
    segments = plan.get('segments') or []
    if segments:
        seconds = sum(s['end'] - s['start'] for s in segments)
        found.append(('segments', say('Yeni kesim: {count} parça, yaklaşık {seconds} sn').format(
            count=len(segments), seconds=f'{seconds:.1f}')))
        transitions = [s['transition'] for s in segments if s.get('transition')]
        if transitions:
            found.append(('transitions', say('{count} geçiş: {names}').format(
                count=len(transitions), names=', '.join(sorted(set(transitions))))))
    removals = {'captions': 'Altyazıları kaldır', 'texts': 'AI yazılarını kaldır', 'marks': 'AI işaretlerini kaldır'}
    for what in plan.get('remove', ()):
        found.append((f'remove:{what}', say(removals.get(what, what))))
    if plan.get('captions'):
        found.append(('captions', say('Altyazı ekle')))
    if plan.get('texts'):
        found.append(('texts', say('{count} ekran yazısı: {texts}').format(
            count=len(plan['texts']), texts=' · '.join(_short(t['text']) for t in plan['texts'][:3]))))
    if plan.get('marks'):
        found.append(('marks', say('{count} işaret (ok / daire)').format(count=len(plan['marks']))))
    if 'color' in plan:
        names = {'brightness': 'parlaklık', 'contrast': 'kontrast', 'saturation': 'doygunluk'}
        found.append(('color', say('Renk: {values}').format(
            values=', '.join(f'{say(names.get(k, k))} {v:+d}' for k, v in plan['color'].items()))))
    if 'speed' in plan:
        found.append(('speed', say('Hız: {value}×').format(value=f'{plan["speed"]:.2f}')))
    if 'aspect' in plan:
        found.append(('aspect', say('Tuval oranı: {value}').format(value=plan['aspect'])))
    if 'volume' in plan:
        found.append(('volume', say('Video sesi: %{value}').format(value=round(plan['volume'] * 100))))
    if 'music_volume' in plan:
        found.append(('music_volume', say('Müzik sesi: %{value}').format(value=round(plan['music_volume'] * 100))))
    if any(key in plan for key in ('title', 'caption', 'hashtags')):
        found.append(('publish', say('Yayın başlığı, açıklaması ve etiketleri')))
    return found


def keep(plan, chosen):
    """The plan with only the chosen parts (keys from parts()); summary and warnings stay."""
    chosen = set(chosen)
    result = {key: value for key, value in plan.items() if key in ('summary', 'warnings')}
    if 'segments' in chosen and plan.get('segments'):
        segments = [dict(s) for s in plan['segments']]
        if 'transitions' not in chosen:
            for segment in segments:
                segment.pop('transition', None)
        result['segments'] = segments
    removals = [what for what in plan.get('remove', ()) if f'remove:{what}' in chosen]
    if removals:
        result['remove'] = removals
    for key in ('captions', 'texts', 'marks', 'color', 'speed', 'aspect', 'volume', 'music_volume'):
        if key in chosen and key in plan:
            result[key] = plan[key]
    if 'publish' in chosen:
        result.update({key: plan[key] for key in ('title', 'caption', 'hashtags') if key in plan})
    return result


def _short(text, limit=28):
    text = ' '.join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


class PlanReviewDialog(QDialog):
    def __init__(self, plan, parent=None, language='tr'):
        super().__init__(parent)
        self.language = language
        self.plan = plan
        self.setWindowTitle(self.tr_(TITLE))
        self.resize(520, 440)
        layout = QVBoxLayout(self)
        summary = QLabel(plan.get('summary') or self.tr_('AI şu değişiklikleri öneriyor:'))
        summary.setWordWrap(True)
        layout.addWidget(summary)
        hint = QLabel(self.tr_('İstemediğiniz kısımların işaretini kaldırın; yalnızca işaretliler uygulanır.'))
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        layout.addWidget(hint)
        holder = QWidget()
        boxes = QVBoxLayout(holder)
        self.boxes = {}
        for key, label in parts(plan, self.tr_):
            box = QCheckBox(label)
            box.setChecked(True)
            box.toggled.connect(self._refresh)
            self.boxes[key] = box
            boxes.addWidget(box)
        boxes.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox()
        self.apply_button = buttons.addButton(self.tr_('Seçilenleri uygula'), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.tr_('İptal'), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def tr_(self, text):
        return i18n.translate(text, self.language)

    def _refresh(self):
        transitions = self.boxes.get('transitions')
        if transitions is not None:  # transitions belong to the new cut
            transitions.setEnabled(self.boxes['segments'].isChecked())
        self.apply_button.setEnabled(bool(self.chosen()))

    def chosen(self):
        picked = {key for key, box in self.boxes.items() if box.isChecked() and box.isEnabled()}
        return picked - {'transitions'} if 'segments' not in picked else picked

    def result_plan(self):
        return keep(self.plan, self.chosen())
