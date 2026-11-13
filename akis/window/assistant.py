"""AI and words: keys, plans, prompt edits, transcripts, captions, voiceover, templates, ideas."""
from __future__ import annotations

from pathlib import Path

from akis.timeline_model import Clip, Track
from akis.media_service import MediaService
from akis.timeline_render import duration_frames
from akis import timeline_service
from akis.ai_service import plan_prompt, add_plan_markers, format_suggestion
from akis.caption_worker import LocalCaptionWorker
from akis.tts_worker import TtsWorker
from akis.ai_workers import AIWorker, PromptEditWorker, TranscriptWorker
from akis import edit_plan
from akis.caption_service import caption_track
from akis import ai_providers
from akis import template_service
from akis import i18n
from akis.template_dialog import TemplateDialog
from akis.inspiration_dialog import InspirationDialog
from akis import speech_settings
from akis import user_templates
from akis import clip_fit, style_sample
from akis.plan_review import PlanReviewDialog
from akis import word_captions
from akis.saved_templates_dialog import SavedTemplatesDialog
from akis.inspiration_service import template_for
from akis.story_dialog import StoryDialog

from PySide6.QtWidgets import QFileDialog, QLineEdit, QMessageBox

from akis import app_support
from akis.app_support import APP_NAME, IDEA_REPLACES_PROMPT_QUESTION, STALE_PLAN_QUESTION, STILL_CLIP_SECONDS, log


class AssistantMixin:
    """AI and words: keys, plans, prompt edits, transcripts, captions, voiceover, templates, ideas."""

    def api_credentials(self) -> tuple[str, str] | None:
        key = self.api_key.text().strip()
        model = self.model.currentText().strip()
        if not key or not model:
            QMessageBox.information(self, APP_NAME, self.ui_text("API anahtarı ve model belirtin."))
            return None
        self._provider_keys[self.provider.currentText()] = key
        if self.remember_key.isChecked():
            self.save_key(key)
        return key, model

    def change_provider(self, provider):
        self._provider_keys[self._active_provider] = self.api_key.text().strip()
        self._active_provider = provider
        self.model.clear(); self.model.addItems(ai_providers.PROVIDERS[provider])
        self.api_key.setPlaceholderText(ai_providers.CLOUDFLARE_KEY_HINT if provider == 'Cloudflare' else "sk-…")
        self.load_key()

    def save_key(self, key: str) -> None:
        if not key:
            self.set_status(self.ui_text('Kaydedilecek API anahtarını girin.'))
            return
        try:
            ai_providers.save_key(APP_NAME, self.provider.currentText(), key)
            self._provider_keys[self.provider.currentText()] = key
            self._saved_providers.add(self.provider.currentText())
            self.remember_key.setChecked(True)
            self.set_status(self.ui_text('API anahtarı sistem kasasına kaydedildi.'))
        except Exception as exc:
            self.set_status(self.ui_text('Anahtar güvenli kasaya kaydedilemedi: {error}', error=exc))

    def on_remember_key_clicked(self, checked: bool) -> None:
        """Unticking "Windows'ta güvenli sakla" removes the stored key of this provider from the vault."""
        if checked:
            return  # saved on the next use or with "Anahtarı güvenli kaydet"
        provider = self.provider.currentText()
        delete_key = getattr(ai_providers, 'delete_key', None)
        if not callable(delete_key):
            self._saved_providers.discard(provider)
            self.set_status(self.ui_text('Anahtar artık kaydedilmeyecek; kayıtlı anahtar bu sürümde silinemiyor.'))
            return
        try:
            delete_key(APP_NAME, provider)
        except Exception as exc:
            log.warning("Anahtar silinemedi (%s): %s", provider, exc)
            self.set_status(self.ui_text('Kayıtlı anahtar silinemedi: {error}', error=exc))
            return
        self._saved_providers.discard(provider)
        self.set_status(self.ui_text('{provider} anahtarı sistem kasasından silindi.', provider=provider))

    def load_key(self) -> None:
        provider = self.provider.currentText()
        key = self._provider_keys.get(provider, '')
        if not key:
            try:
                key = ai_providers.load_key(APP_NAME, provider)
                if key:
                    self._saved_providers.add(provider)
            except Exception:
                key = ''
        self.api_key.setText(key)
        self.remember_key.setChecked(provider in self._saved_providers)

    def change_transcript_provider(self, provider):
        self.transcript_model.clear()
        self.transcript_model.addItems(ai_providers.TRANSCRIPTION_MODELS.get(provider, ()))

    def show_templates(self):
        """Şablonlar: ready-made structure (tracks, aspect ratio, colour style, tempo)."""
        code = self.ui_language()
        aspect = i18n.translate(str(self.aspect.currentData() or ""), code).split(" · ")[0]
        dialog = TemplateDialog(self, language=code, current_aspect=aspect, timeline=self.multitrack)
        result = dialog.exec()
        if result == TemplateDialog.SAVED:
            self.show_saved_templates()
        elif result and dialog.selection()[0] is not None:
            self.apply_template_choice(*dialog.selection())

    def show_saved_templates(self):
        """Şablonlarım: templates the user saved from their own projects."""
        folder = app_support.app_data_dir()
        dialog = SavedTemplatesDialog(self, saved=user_templates.load(folder), language=self.ui_language(),
                                      save=lambda name: user_templates.add(folder, self.capture_template(name)),
                                      delete=lambda name: user_templates.remove(folder, name))
        if dialog.exec() and dialog.selection() is not None:
            self.apply_saved_template(dialog.selection())

    def style_from_sample(self):
        """Read a finished video's look (akis.style_sample), save it as a template of the user's own and,
        when the user agrees, apply it to this project."""
        if not self.can_start_work():
            return
        chosen, _ = QFileDialog.getOpenFileName(self, self.ui_text('Stili alınacak örnek video'), '',
                                                'Video (*.mp4 *.mov *.mkv *.webm *.avi *.m4v)')
        if not chosen:
            return
        main = next((track for track in self.multitrack.tracks if track.kind == 'video'), None)
        own = next((clip.source for clip in (main.clips if main else []) if clip.source), None)
        media = MediaService(app_support.ffmpeg_path())
        self.run_analysis(self.ui_text('Örnek videonun stili okunuyor…'),
                          lambda: style_sample.measure(media, chosen, own),
                          lambda found: self.finish_style_sample(found, chosen))

    def finish_style_sample(self, found, chosen):
        name = user_templates.clean_name(self.ui_text('Örnek: {name}', name=Path(chosen).stem))
        item = style_sample.to_template(found, name)
        lines = style_sample.describe(found, item, self.ui_template)
        question = '\n'.join([self.ui_text('Örnek videoda bulunanlar:'), ''] + lines + ['', self.ui_text(
            '“{name}” adıyla Şablonlarım’a kaydedilip bu projeye uygulansın mı?', name=name)])
        if QMessageBox.question(self, APP_NAME, question, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes:
            return
        try:
            user_templates.add(app_support.app_data_dir(), item)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.apply_saved_template(user_templates._valid(item))

    def capture_template(self, name):
        """The open project's structure and settings as a template of the user's own."""
        return user_templates.capture(
            name, self.multitrack, aspect=self.aspect.currentData(),
            color=(self.brightness.value(), self.contrast.value(), self.saturation.value()),
            speed=self.speed_value(), audio=self.render_adjustments().get('audio', ()))

    def apply_saved_template(self, item):
        with self.history_step():
            user_templates.apply(self.multitrack, item)
            if item.get('framing'):                 # a look taken from a sample video
                for track in self.multitrack.tracks:
                    if track.kind == 'video':
                        for clip in track.clips:
                            clip_fit.apply(clip, item['framing'])
            self._template_before_video = not bool(self.state.source)
            if item['aspect']:
                self.select_aspect(item['aspect'])
            self.apply_preset(*item['color'])
            self.select_speed(item['speed'])
        for box, name in self.audio_boxes():
            box.setChecked(name[len('audio_'):] in item['audio'])
        self.multitrack_view.set_model(self.multitrack)
        self.refresh_timeline_view()
        self.multitrack_view.update()
        if duration_frames(self.multitrack):
            self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('{name} uygulandı; medyayı izlere ekleyin.', name=item['name']))

    def show_inspiration(self):
        """İlham: creative ideas. An idea becomes the edit request; its matching template is optional."""
        dialog = InspirationDialog(self, language=self.ui_language())
        if not dialog.exec():
            return
        idea, action = dialog.selection()
        if idea is None:
            return
        current = self.ai_prompt.toPlainText().strip()
        if current and current != idea.prompt.strip():
            # The edit request is the user's own text and the box has no undo across setPlainText.
            answer = QMessageBox.question(self, APP_NAME, self.ui_text(IDEA_REPLACES_PROMPT_QUESTION),
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.set_status(self.ui_text('Kurgu isteğiniz korundu; fikir uygulanmadı.'))
                return
        self.ai_prompt.setPlainText(idea.prompt)
        template = template_for(idea) if action == 'prompt+template' else None
        if template is not None:
            self.apply_template_choice(template, template.style, template.tempo)
            self.set_status(self.ui_text('“{idea}” fikri kurgu isteğine yazıldı ve {layout} şablonu uygulandı.',
                                         idea=idea.title, layout=template.name))
        else:
            self.set_status(self.ui_text('“{idea}” fikri kurgu isteğine yazıldı; AI sekmesinden uygulayabilirsiniz.',
                                         idea=idea.title))

    # Hikâye Stüdyosu: Gemini text → image → video; results are added to the project as media.
    def gemini_key(self) -> str:
        if self.provider.currentText() == 'Gemini' and self.api_key.text().strip():
            return self.api_key.text().strip()
        key = self._provider_keys.get('Gemini', '')
        if not key:
            try:
                key = ai_providers.load_key(APP_NAME, 'Gemini')
            except Exception:  # keyring backend missing or locked
                key = ''
        return key

    def story_output_dir(self) -> str:
        """Generated media lives beside the project file, or in the app-data folder for an untitled project."""
        if self.project_path:
            project = Path(self.project_path)
            folder = project.with_name(project.name.removesuffix('.akis.json').removesuffix('.json') + '_ai')
        else:
            folder = app_support.app_data_dir() / 'generated'
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    def add_generated_media(self, path: str) -> bool:
        """Put a generated file on the timeline. A still image becomes a short clip, since tracks hold video."""
        file = Path(path)
        if not file.is_file():
            return False
        if file.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
            clip = file.with_name(file.stem + '_klip.mp4')
            result = MediaService(app_support.ffmpeg_path()).run(
                ['-y', '-loop', '1', '-t', str(STILL_CLIP_SECONDS), '-i', str(file), '-r', '30',
                 '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p', '-c:v', 'libx264', '-an', str(clip)], text=True)
            if result.returncode != 0 or not clip.is_file():
                QMessageBox.warning(self, APP_NAME, 'Görsel klibe dönüştürülemedi.')
                return False
            file = clip
        before = len(self.media_bin.paths)
        self.add_video(str(file))
        return bool(self.state.source) and (len(self.media_bin.paths) > before or str(file) in self.media_bin.paths)

    def show_story_studio(self):
        if self.story_dialog is None:
            self.story_dialog = StoryDialog(self, api_key=self.gemini_key, output_dir=self.story_output_dir,
                                            add_media=self.add_generated_media,
                                            default_aspect=str(self.aspect.currentData() or '16:9'))
        self.story_dialog.show()
        self.story_dialog.raise_()
        self.story_dialog.activateWindow()

    def apply_template_choice(self, template, style, tempo):
        with self.history_step():
            template_service.apply_template(self.multitrack, template)
            self._template_before_video = not bool(self.state.source)
            self.select_choice(self.aspect, i18n.choice_key(i18n.ASPECTS, template.ratio))
            self.apply_preset(*template_service.STYLES[style])
            self.select_speed(template_service.TEMPOS[tempo])
        self.multitrack_view.set_model(self.multitrack)
        self.refresh_timeline_view()
        self.multitrack_view.update()
        if duration_frames(self.multitrack):
            self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('{name} uygulandı; medyayı izlere ekleyin.', name=template.name))

    def toggle_key(self) -> None:
        mode = self.api_key.echoMode()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Normal if mode == QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password)

    def run_ai(self) -> None:
        if not self.can_start_work():
            return
        if not self.ensure_video():
            return
        credentials = self.api_credentials()
        if not credentials:
            return
        key, model = credentials
        self.worker = AIWorker(key, model, self.state.source, self.state.duration, plan_prompt(self.ai_prompt.toPlainText().strip(), self.ai_platform.currentData(), self.ai_tempo.currentData(), self.ai_style.currentData(), self.ai_focus.currentData()), app_support.ffmpeg_path(), self.provider.currentText())
        self.begin_work("AI analizi başlatılıyor…")
        self.worker.status.connect(self.set_status)
        self.worker.completed.connect(self.on_ai_plan)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.cancelled.connect(self.on_worker_cancelled)
        self.start_worker()

    def edit_sources(self):
        """Every video on the timeline (then the loaded one), in a stable order with durations."""
        paths = []
        for track in self.multitrack.tracks:
            if track.kind == 'video':
                for clip in sorted(track.clips, key=lambda c: c.start):
                    if clip.source and clip.source not in paths:
                        paths.append(clip.source)
        if self.state.source and self.state.source not in paths:
            paths.append(self.state.source)
        media = MediaService(app_support.ffmpeg_path())
        return [(path, media.duration(path)) for path in paths if Path(path).is_file()]

    def run_prompt_edit(self) -> None:
        if not self.can_start_work() or not self.ensure_video():
            return
        request = self.ai_prompt.toPlainText().strip()
        if not request:
            QMessageBox.information(self, APP_NAME, "Önce videoyu nasıl kurgulamak istediğinizi yazın.")
            return
        credentials = self.api_credentials()
        if not credentials:
            return
        key, model = credentials
        try:
            sources = self.edit_sources()
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f'Video okunamadı: {exc}')
            return
        if not sources:
            QMessageBox.warning(self, APP_NAME, 'Kurgulanacak video dosyası bulunamadı.')
            return
        transcripts = {self.caption_source: self.caption_segments} if self.caption_source and self.caption_segments else {}
        self._prompt_revision = self.timeline_revision()
        self.begin_work("Prompt kurgusu başlatılıyor…")
        # The model sets colour/speed/aspect as absolute values, so it is told what they are now.
        settings = {'color': (self.brightness.value(), self.contrast.value(), self.saturation.value()),
                    'speed': self.speed.currentText(), 'aspect': self.aspect.currentData()}
        self.worker = PromptEditWorker(key, model, self.provider.currentText(), request, self.multitrack, sources,
                                       app_support.ffmpeg_path(), transcripts,
                                       self.local_model.currentText() if self.use_speech.isChecked() else None,
                                       settings=settings)
        self.worker.status.connect(self.set_status)
        self.worker.completed.connect(self.on_prompt_edit)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.cancelled.connect(self.on_worker_cancelled)
        self.start_worker()

    def on_prompt_edit(self, plan, sources):
        if self._shutting_down:  # a result that arrives while the window closes is dropped
            return
        started, self._prompt_revision = self._prompt_revision, None
        if started is not None and started != self.timeline_revision():
            # The plan was computed from the timeline as it was when the request started.
            answer = QMessageBox.question(self, APP_NAME, STALE_PLAN_QUESTION,
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.finish_work('AI planı uygulanmadı; zaman çizelgesindeki değişiklikleriniz korundu.')
                return
        # A window nobody sees (tests, scripted runs) has nobody to ask: the plan is applied as it is.
        if self.review_plan.isChecked() and self.isVisible():
            review = PlanReviewDialog(plan, self, language=self.ui_language())
            if not review.exec():
                self.finish_work(self.ui_text('AI planı uygulanmadı.'))
                return
            plan = review.result_plan()
        try:
            aspect = self.aspect.currentData()
            if 'aspect' in plan:  # a bare ratio such as '16:9'
                aspect = i18n.choice_key(i18n.ASPECTS, plan['aspect'])
                if aspect is None:
                    raise ValueError(f'desteklenmeyen oran: {plan["aspect"]}')
            canvas = timeline_service.canvas_size(aspect, self.multitrack, MediaService(app_support.ffmpeg_path()))
            timeline = edit_plan.apply_plan(self.multitrack, sources, plan, canvas)
        except Exception as exc:
            self.on_worker_error(f'Kurgu planı uygulanamadı: {exc}')
            return
        with self.history_step():  # the whole AI edit, settings included, is one undo step
            if 'aspect' in plan:
                self.select_choice(self.aspect, aspect)
            if 'speed' in plan:
                self.select_speed(plan['speed'])
            if 'color' in plan:
                # A plan carries only the colour keys the model gave; the others keep their current value.
                color = plan['color']
                self.apply_preset(color.get('brightness', self.brightness.value()),
                                  color.get('contrast', self.contrast.value()),
                                  color.get('saturation', self.saturation.value()))
            if 'title' in plan:
                self.publish_title.setText(plan['title'])
            if 'caption' in plan:
                self.publish_caption.setPlainText(plan['caption'])
            if 'hashtags' in plan:
                self.publish_tags.setPlainText(' '.join(t if t.startswith('#') else '#' + t for t in plan['hashtags']))
            self.show_timeline(timeline)
        self.ai_result.setPlainText(edit_plan.describe(plan, timeline))
        self.finish_work('AI kurgusu uygulandı. Beğenmezseniz geri alabilir veya yeni bir istek yazabilirsiniz.')

    def on_ai_plan(self, plans):
        if self._shutting_down:
            return
        self.ai_suggestions = plans
        self.ai_choice.clear()
        self.ai_choice.addItems([str(p.get('title') or f'Öneri / Suggestion {i+1}') for i, p in enumerate(plans)])
        self.show_ai_suggestion(self.ai_choice.currentIndex())
        self.finish_work('Öneriler hazır; birini seçip işaret olarak uygulayabilirsiniz.')

    def show_ai_suggestion(self, index):
        if 0 <= index < len(self.ai_suggestions):
            plan = self.ai_suggestions[index]
            self.ai_result.setPlainText(format_suggestion(plan))

    def apply_ai_suggestion(self):
        index = self.ai_choice.currentIndex()
        if 0 <= index < len(self.ai_suggestions):
            plan = self.ai_suggestions[index]
            with self.history_step():
                add_plan_markers(self.multitrack, plan)
                self.publish_title.setText(str(plan.get('title', '')))
                self.publish_caption.setPlainText(str(plan.get('caption', '')))
                if plan.get('hashtags'):
                    self.publish_tags.setPlainText(' '.join('#' + str(tag).lstrip('#') for tag in plan['hashtags']))
            self.set_status(self.ui_text('Öneri işaretleri projeye eklendi.'))
            self.multitrack_view.update()
        else:
            self.set_status(self.ui_text('Önce “Öneri al” ile öneri isteyin.'))

    def run_transcript(self) -> None:
        if not self.can_start_work():
            return
        if not self.ensure_video():
            return
        if self.caption_backend.currentIndex() == 1:
            self.caption_request_source = self.state.source
            self.worker = LocalCaptionWorker(self.caption_request_source, self.local_model.currentText(), self.download_model.isChecked())
        else:
            provider = self.caption_backend.currentText()
            if self.provider.currentText() == provider:
                key = self.api_key.text().strip()
            else:
                key = self._provider_keys.get(provider, '')
                if not key:
                    try:
                        key = ai_providers.load_key(APP_NAME, provider)
                    except Exception:
                        key = ''
            if not key or not self.transcript_model.currentText().strip():
                QMessageBox.information(self, APP_NAME, f'{provider} için API anahtarı ve modeli girin.')
                return
            self.worker = TranscriptWorker(key, self.state.source, app_support.ffmpeg_path(), self.transcript_model.currentText().strip(), provider)
            source = self.state.source
            self.worker.timed.connect(lambda segments: self.on_cloud_segments(segments, source))
        self.begin_work("Ses hazırlanıyor…")
        self.worker.status.connect(self.set_status)
        self.worker.completed.connect(self.on_local_transcript if self.caption_backend.currentIndex() == 1 else self.on_transcript)
        self.worker.failed.connect(self.on_worker_error)
        if hasattr(self.worker, 'cancelled'):  # local Whisper runs in one call and cannot be stopped
            self.worker.cancelled.connect(self.on_worker_cancelled)
        self.start_worker()

    def on_local_transcript(self, segments):
        if self._shutting_down:
            return
        self.caption_segments = segments
        self.caption_source = self.caption_request_source
        self.apply_captions_button.setEnabled(bool(segments))
        self.on_transcript(' '.join(segment['text'] for segment in segments))

    def on_cloud_segments(self, segments, source):
        """A cloud service gave timings: the transcript can make captions, as a local one does."""
        if self._shutting_down or not segments:
            return
        self.caption_segments = segments
        self.caption_source = source
        self.apply_captions_button.setEnabled(True)

    def apply_local_captions(self):
        with self.history_step():
            # Applying again replaces the previous caption track instead of drawing the captions twice.
            self.multitrack.tracks = [track for track in self.multitrack.tracks
                                      if not (track.kind == 'text' and track.name == edit_plan.CAPTION_TRACK)]
            self.multitrack_view.selected = self.multitrack_view.selected_track = None
            look = word_captions.CHOICES[max(0, self.caption_look.currentIndex())]
            count = caption_track(self.multitrack, self.caption_source, self.caption_segments, look)
        self.refresh_timeline_view()
        self.multitrack_view.update()
        self.seek_timeline(self.timeline_frame)
        self.set_status(self.ui_text('{count} altyazı klibi eklendi.', count=count))

    def create_voiceover(self):
        if not self.can_start_work():
            return
        text = self.tts_input.toPlainText().strip()
        if not text:
            self.set_status(self.ui_text('Önce seslendirme metni girin.'))
            return
        chosen, _ = QFileDialog.getSaveFileName(self, 'Seslendirmeyi kaydet', '', 'WAV (*.wav)')
        if not chosen:
            return
        path = chosen if chosen.lower().endswith('.wav') else chosen + '.wav'
        if not self.confirm_overwrite(chosen, path):
            return
        self.begin_work('Windows sesi oluşturuluyor…')
        self._voiceover_at = self.timeline_frame if self.tts_to_timeline.isChecked() else None
        self.worker = TtsWorker(text, path, voice_id=self.tts_voice.currentData(),
                                language=speech_settings.language() or 'tr')
        self.worker.completed.connect(self.on_voiceover)
        self.worker.failed.connect(self.on_worker_error)
        self.start_worker()

    def on_voiceover(self, path: str) -> None:
        if self._shutting_down:
            return
        frame = getattr(self, '_voiceover_at', None)
        if frame is None:
            self.finish_work(self.ui_text('Ses kaydedildi: {path}', path=path))
            return
        try:
            seconds = MediaService(app_support.ffmpeg_path()).duration(path)
        except (ValueError, RuntimeError, OSError):
            seconds = 0
        if seconds <= 0:
            self.finish_work(self.ui_text('Ses kaydedildi: {path}', path=path))
            return
        with self.history_step():
            self.place_voiceover(path, frame, seconds)
        self.refresh_timeline_view()
        self.media_bin.add(path)
        self.refresh_media_bin()
        self.seek_timeline(self.timeline_frame)
        self.finish_work(self.ui_text('Seslendirme zaman çizelgesine eklendi: {name}', name=Path(path).name))

    def place_voiceover(self, path, frame, seconds):
        """Put a voiceover on a “Seslendirme” track at `frame`, on a new one when the old one is busy there."""
        fps = self.multitrack.fps_num / self.multitrack.fps_den
        clip = Clip(path, frame, max(1, round(seconds * fps)), source_length=max(1, round(seconds * fps)))
        for track in self.multitrack.tracks:
            if track.kind == 'audio' and track.name.startswith('Seslendirme'):
                try:
                    track.add(clip)
                    return clip
                except ValueError:
                    continue
        names = {track.name for track in self.multitrack.tracks}
        name = next(n for n in ('Seslendirme', *(f'Seslendirme {i}' for i in range(2, 100))) if n not in names)
        self.multitrack.tracks.append(Track('audio', name, [clip]))
        return clip

    def on_transcript(self, text: str) -> None:
        if self._shutting_down:
            return
        self.ai_result.setPlainText("KONUŞMA METNİ\n\n" + text)
        if not self.publish_caption.toPlainText().strip():
            self.publish_caption.setPlainText(text)
        self.finish_work("Türkçe konuşma metni hazır.")
