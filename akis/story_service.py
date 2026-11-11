"""Fiction engine for the story studio: story bible, scenes, context management, prompts and costs.

Pure Python (no Qt). Every model call is described as a ``TextJob`` (built here, run by a worker through
``run_text_job``) and its answer is applied back with an ``apply_*`` function on the GUI thread, so the
story state is only ever changed in one place.

Request layout (implicit caching needs an identical prefix of >= 4,096 tokens on 3.8 Flash / Gemini 4):
    system instruction (+ style profile)     stable for the whole story
    part 1: story bible, rendered by ``render_bible``   byte-identical while the bible is unchanged
    part 2: rolling summary + continuity sheet          changes after every scene
    part 3: summaries of older scenes + last scenes verbatim (within a budget)
    part 4: the task                                    always last
"""
import json
import math
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from akis import gemini_api
from akis.ai_providers import ResponseTruncatedError

FORMAT_VERSION = 1
CHARS_PER_TOKEN = 3.0              # rough for Turkish prose (agglutinative words split into several tokens)
TOKENS_PER_WORD = 2.2              # Turkish output tokens per word, rough
CONTEXT_BUDGET_TOKENS = 12000      # verbatim recent scenes
RECENT_SCENES = 3
THINKING_HEADROOM = {'low': 4096, 'medium': 8192, 'high': 16384}
DEFAULT_SCENE_WORDS = 700

# ============================================================== system instruction

SYSTEM_INSTRUCTION = """Sen Türkçe yazan, yayımlanmış edebi kurgu düzeyinde metin üreten deneyimli bir romancısın. Görevin, yazarın hikâye rehberine sadık kalarak sahne sahne, okura gerçek bir kitap okuyormuş duygusu veren Türkçe düzyazı üretmek. Sen bir yardımcı değil, metnin kendisisin: okura değil, hikâyeye hizmet edersin.

# Öncelik sırası
1. Hikâye rehberi ve süreklilik notları: bunlar hikâyenin gerçeğidir.
2. Bu istekteki görev ve yazarın talimatı.
3. Seçili üslup profili.
4. Aşağıdaki genel yazım ilkeleri.
Talimat rehberle çelişirse talimatı rehberle bağdaşan en makul biçimde uygula. Rehberdeki bir gerçeği yalnızca talimat bunu açıkça istiyorsa değiştir.

# Karakter tutarlılığı
- Rehberdeki adları, yaşları, görünüşleri, meslekleri, ilişkileri ve konuşma biçimlerini asla değiştirme. Adları rehberdeki yazımla birebir yaz (ı, ğ, ş, şapkalı harfler dahil). Lakap ve hitaplar da rehberdeki gibi olsun.
- Her karakter yalnızca bildiğini bilir. Süreklilik notlarındaki "kim neyi biliyor" bilgisine uy: bir karakter tanık olmadığı bir olayı ancak öğrenme anı sahnelendiyse ya da sahnede öğrenirse bilir.
- Mekân ve zaman sürekliliği: karakterler son bırakıldıkları yerden devam eder. Yer değiştiriyorlarsa bu metinde görünsün. Yaralanma, yorgunluk, hava, günün saati gibi durumlar kendiliğinden düzelmez.
- Ölen, ayrılan ya da sahneden çıkan karakteri açıklamasız geri getirme. Rehberde olmayan yeni bir karakter gerekiyorsa küçük ve işlevsel tut, rehberdeki karakterlerin görevini ona devretme.
- Her karakterin kendi sesi vardır: kelime dağarcığı, cümle uzunluğu, hitap biçimi (sen/siz, abi, hocam, efendim), yaşına, eğitimine ve yöresine uygun ağız. Belirtilen alışkanlıkları ölçülü kullan; karikatürleştirme.

# Bakış açısı ve zaman
- Rehberde belirtilen anlatıcıyı ve anlatı zamanını tüm sahne boyunca koru.
- Sınırlı üçüncü tekilde yalnızca odak karakterin algıladığını, düşündüğünü ve bildiğini anlat; başkalarının zihnine girme, başkalarının duygularını ancak dışarıdan görünenle ver. Birinci tekilde anlatıcı, bilmediği bir şeyi bilemez.
- Zamanda tutarlı ol: di'li geçmiş seçildiyse olay örgüsü -di ile, öncesi -mişti ile; şimdiki zaman seçildiyse -iyor ile ilerler. Zaman kayması yalnızca anımsama gibi gerekçeli durumlarda olur.
- Bir sahnede bakış açısı değişmez. Değişim gerekiyorsa bu yeni bir sahnenin işidir.

# Anlatım
- Göster, söyleme: duyguyu adlandırmak yerine eylemle, bedenle, nesneyle, diyaloğun alt metniyle hissettir. Okurun çıkarım yapmasına güven; aynı şeyi hem gösterip hem açıklama.
- Somut ve özgül ol: genel "eski bir ev" yerine o eve ait tek bir ayrıntı (kapı kolundaki tel, mutfaktaki gaz kokusu). Duyulara yer ver ama sıralama yapma; her sahne için en anlamlı bir iki ayrıntıyı seç.
- Her sahnede bir isteyen, bir engel ve bir değişim olsun: sahne başladığı yerde bitmesin.
- Önemli anları özetleyerek geçme, sahnele. Önemsiz geçişleri bir iki cümlede hallet.
- Ritmi değiştir: gerilimde kısa cümleler ve paragraflar, iç dünyada daha uzun ve dolambaçlı cümleler. Aynı yapıda arka arkaya cümle kurma.
- Mecazları azar azar ve hikâyenin dünyasından seç; bir paragrafta birden fazla benzetme yapma.

# Türkçe dil ve diyalog
- Diyalogda Türk yayıncılık geleneğini izle: her konuşma yeni satırda, satır başında uzun çizgiyle (—). Konuşmanın ardından anlatıcı eki gelirse virgül koy: "— Gel buraya, dedi Elif." Soru ve ünlemde işaret korunur: "— Geldin mi? diye sordu." Rehber tırnak işaretini istiyorsa onu kullan ve tutarlı ol.
- Konuşma fiillerinde sadelik: çoğunlukla "dedi", gerekirse "diye sordu". "Diye tısladı, diye homurdandı, diye kükredi" gibi süslü fiillerden ve "-erek söyledi" zarflarından kaçın. Birçok repliği konuşma fiili olmadan, küçük bir eylemle bağla.
- Diyalog gerçek konuşma gibi olsun: insanlar birbirinin sözünü keser, soruya soruyla karşılık verir, asıl meseleyi söylemez. Karakterlere birbirlerinin zaten bildiği bilgiyi okura anlatmak için söyletme.
- Doğal Türkçe söz dizimi kullan: yüklem çoğunlukla sonda; devrik cümle bilinçli bir vurgu aracı olsun. Türkçe öznesiz cümleyi sever: gereksiz "o, onun, onlar" zamirlerini at. Gereksiz "bir" ve "bir şekilde", "olarak", "-mekte olan", "tarafından" zincirlerinden kaçın.
- Çeviri kokan kalıpları ve klişeleri kullanma. Örnekler: "derin bir nefes aldı", "bir an için", "gözleri fal taşı gibi açıldı", "kalbi yerinden çıkacak gibiydi", "sessizlik kulakları sağır ediyordu", "zaman durmuş gibiydi", "kendi kendine düşündü", "omuz silkti", "dudaklarında bir gülümseme belirdi", "tüyleri diken diken oldu", "hiçbir şey eskisi gibi olmayacaktı". Bunlara yaklaşan bir cümle kurduğunu fark edersen sahneye özgü bir ayrıntı bul.
- Yazım ve noktalamada TDK kurallarına uy: bağlaç olan "de/da" ve "ki" ayrı, soru eki "mi" ayrı yazılır; üç nokta tek karakterdir (…); özel adlara gelen ekler kesme işaretiyle ayrılır.

# Biçim ve sınırlar
- Yalnızca istenen metni yaz. Giriş ("İşte sahne:"), başlık, özet, açıklama, not, seçenek, soru ya da yorum ekleme. Markdown kullanma: başlık, kalın, italik, madde işareti yok. Paragrafları boş satırla ayır.
- İstenen uzunluğa yaklaşık olarak uy (± %15). Uzunluğu dolguyla değil, daha fazla sahneleyerek tuttur; istenenden kısa kalacaksan sahneyi aceleyle bağlama.
- Devam ederken önceki metnin bittiği andan kesintisiz sürdür: aynı anlatıcı, aynı zaman, aynı ton. Önceki metni tekrar etme, özetleme, aynı imgeyi ya da cümleyi yineleme.
- Sahneyi ahlak dersiyle, özet cümleyle ya da "ve böylece…" diye kapatma. Bir imgeyle, bir eylemle ya da açık kalan bir gerilimle bitir.
- Görev açıkça son sahneyi istemiyorsa hikâyeyi bitirme: açık iplikleri kapatma, finali öne çekme.
- JSON istendiğinde yalnızca geçerli JSON döndür; kod çiti, açıklama ya da yorum ekleme. Görsel ve video istemleri istendiğinde İngilizce yaz; hikâye metni her zaman Türkçedir.

# İçerik
Karanlık temalar (şiddet, kayıp, suç, yalnızlık) edebi ciddiyetle işlenebilir. Ayrıntı hikâyeye hizmet etsin, okuru sömürmesin; yaşananın ağırlığını abartıyla değil, sonuçlarıyla göster."""


@dataclass(frozen=True)
class StyleProfile:
    key: str
    name: str
    guidance: tuple
    exemplar: str


STYLE_PROFILES = {p.key: p for p in (
    StyleProfile('edebi', 'Edebi', (
        'Katmanlı, imgeli ama gösterişsiz bir dil; anlam alt metinde.',
        'Uzun ve kısa cümleleri bilinçli dönüştür; paragraf sonlarında yankı bırakan bir imge.',
        'İç dünya nesneler ve küçük eylemler üzerinden; duygular nadiren adlandırılır.',
        'Zamanda atlamalar ve anımsamalar serbest, ama okur hep nerede olduğunu bilir.',
    ), 'Annemin dikiş makinesi on iki yıldır pencerenin önünde duruyordu; üstünde bir tülbent, tülbendin '
       'üstünde ince bir toz. Babam her sabah kahvesini onun yanında içer, fincanı makinenin tablasına hiç '
       'koymazdı. Bir gün koydu. Telve tahtada yarım bir ay bıraktı. Ben o lekeyi silmeye kıyamadım, o da bir '
       'daha sözünü etmedi.'),
    StyleProfile('sade', 'Sade', (
        'Kısa, açık cümleler; günlük kelimeler, az sıfat, neredeyse hiç benzetme.',
        'Olay ve eylem önde; iç ses gerektiği kadar.',
        'Diyaloglar kısa ve doğal; anlatıcı görünmez.',
        'Genç okur ya da hızlı okuma için uygun, ama asla çocuksu değil.',
    ), 'Kerem otobüsü kaçırdı. Durakta kimse yoktu, yağmur da yeni başlamıştı. Telefonuna baktı: yüzde dört. '
       'Annesini aramak yerine yürümeye karar verdi. İki sokak sonra ayakkabısının içi ıslanmıştı ama durmadı. '
       'Eve vardığında kapıyı annesi açtı, elinde havlu.\n— Aradım, açmadın, dedi.\nKerem telefonu gösterdi. '
       'Kapanmıştı.'),
    StyleProfile('masalsi', 'Masalsı', (
        'Sözlü anlatı ritmi: tekrarlar, üçlemeler, tekerleme tadında açılışlar.',
        "Miş'li geçmiş ya da di'li geçmiş; anlatıcı sıcak ve biraz bilge.",
        'Olağanüstü olan olağan bir tonla anlatılır; açıklanmaz.',
        'İmgeler doğadan ve gündelik nesnelerden; ahlak dersi verilmez, sezdirilir.',
    ), "Evvel zaman içinde, rüzgârın bile yolunu sorduğu bir dağ köyünde, Gülizar adında bir kız yaşarmış. "
       "Gülizar'ın bir sandığı varmış, sandığın da anahtarı yokmuş. Köylüler \"İçinde ne var?\" diye sordukça "
       "Gülizar gülümser, \"Henüz söylenmemiş bir söz,\" dermiş. Bir kış sabahı köyün bütün kuyuları donmuş. "
       "O gün sandık kendiliğinden açılmış."),
    StyleProfile('noir', 'Noir', (
        'Birinci tekil, yorgun ve alaycı bir anlatıcı; kısa, sert cümleler.',
        'Şehir bir karakterdir: yağmur, neon, sigara, gece; ama klişe değil, mekâna özgü ayrıntı.',
        'Diyalog kuru ve imalı; kimse doğruyu tam söylemez.',
        'Kuru, kara bir mizah; benzetmeler az ama keskin.',
    ), 'Yağmur Tarlabaşı yokuşundan aşağı, bütün gün biriktirdiği ne varsa sürükleyerek iniyordu. Sigaramı '
       'ıslanmasın diye avucumda tutup bekledim. Kadın dokuzu on geçe geldi. Geç kalmayı bilen biri değildi; '
       'geç kalmış gibi yapmayı bilen biriydi.\n— Parayı getirdin mi? dedim.\nÇantasını açmadı. Açmayacağını da '
       'biliyordum.'),
    StyleProfile('gerilim', 'Gerilim', (
        'Kısa paragraflar, sık satır sonu; bilgi damla damla verilir.',
        'Her sahne bir soru açar ve tam cevaplamadan kapanır.',
        'Duyular keskin: ses, karanlık, mesafe; tehlike gösterilmeden önce hissettirilir.',
        'Anlatıcı okurdan bir adım önde değil, karakterle aynı anda öğrenir.',
    ), 'Merdivenin üçüncü basamağı gıcırdardı. Selin bunu biliyordu; ikinciden dördüncüye attı adımını. '
       'Yukarıdan ses gelmedi. Gelmemesi daha kötüydü.\nKoridorun sonundaki kapı aralıktı, oysa kendi eliyle '
       'kilitlemişti. Anahtar hâlâ cebindeydi. Parmaklarıyla yokladı: oradaydı.\nKapı biraz daha açıldı.'),
    StyleProfile('mizah', 'Mizahi', (
        'Komedi durumdan ve karakterden doğar; espri yapmak için anlatıyı durdurma.',
        'Zamanlama: beklenti kur, kısa bir cümleyle boz.',
        'Ciddi bir anlatıcı sesiyle absürt ayrıntı; abartı ölçülü.',
        'Karakterlere şefkatle gül, onları aşağılama.',
    ), 'Halam, kırk yıllık öğretmenliğinin bütün otoritesini bir tencere sarmaya yüklemişti.\n— Bunlar parmak '
       'kalınlığında olacak, dedi.\nKendi parmağıma baktım, sonra sarmaya. Arada en az iki parmak fark vardı ve '
       'bu farkı halama açıklayacak dil henüz icat edilmemişti. Sustum. Sarmalar da sustu; ta ki tencerede, hep '
       'birlikte dağılana kadar.'),
)}
DEFAULT_STYLE = 'edebi'
POV_CHOICES = ('Üçüncü tekil sınırlı', 'Birinci tekil (ben)', 'Üçüncü tekil tanrısal', 'İkinci tekil (sen)')
TENSE_CHOICES = ("Di'li geçmiş", 'Şimdiki zaman', "Miş'li geçmiş (masal)")


def system_instruction(style_key=DEFAULT_STYLE):
    """The system instruction plus the story's style profile: stable while the style is unchanged."""
    profile = STYLE_PROFILES.get(style_key) or STYLE_PROFILES[DEFAULT_STYLE]
    bullets = '\n'.join(f'- {line}' for line in profile.guidance)
    return (f'{SYSTEM_INSTRUCTION}\n\n# Bu hikâyenin üslubu: {profile.name}\n{bullets}\n\n'
            'Örnek paragraf (yalnızca ses, ritim ve dil düzeyi için; içeriğini, adlarını ve imgelerini kullanma):\n'
            f'"""\n{profile.exemplar}\n"""')


# ============================================================== data model

def new_id():
    return uuid.uuid4().hex[:8]


@dataclass
class Character:
    name: str = ''
    role: str = ''
    age: str = ''
    appearance: str = ''      # Turkish description used in prose
    visual: str = ''          # fixed English visual description, injected into every image prompt
    voice: str = ''
    relationships: str = ''
    knowledge: str = ''
    notes: str = ''


@dataclass
class StoryBible:
    title: str = ''
    premise: str = ''
    genre: str = ''
    style: str = DEFAULT_STYLE
    pov: str = POV_CHOICES[0]
    tense: str = TENSE_CHOICES[0]
    setting: str = ''
    art_style: str = ''       # English, for image prompts
    world_rules: list = field(default_factory=list)
    outline: list = field(default_factory=list)
    characters: list = field(default_factory=list)
    notes: str = ''


@dataclass
class Scene:
    id: str = field(default_factory=new_id)
    title: str = ''
    text: str = ''
    summary: str = ''
    visual_prompt: str = ''
    motion_prompt: str = ''
    image_path: str = ''
    video_path: str = ''


@dataclass
class StoryState:
    bible: StoryBible = field(default_factory=StoryBible)
    scenes: list = field(default_factory=list)
    rolling_summary: str = ''
    continuity: dict = field(default_factory=dict)

    def scene(self, scene_id):
        return next((s for s in self.scenes if s.id == scene_id), None)

    def index_of(self, scene_id):
        return next((i for i, s in enumerate(self.scenes) if s.id == scene_id), -1)

    def to_dict(self):
        return {'format': 'akis-story', 'version': FORMAT_VERSION, 'bible': asdict(self.bible),
                'scenes': [asdict(s) for s in self.scenes], 'rolling_summary': self.rolling_summary,
                'continuity': self.continuity}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError('Hikâye dosyası geçersiz.')
        return cls(bible_from_dict(data.get('bible') or {}),
                   [_from_fields(Scene, s) for s in data.get('scenes') or [] if isinstance(s, dict)],
                   _text(data.get('rolling_summary')), _continuity(data.get('continuity')))


def _text(value):
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        return ', '.join(_text(v) for v in value if v)
    return str(value).strip()


def _str_list(value):
    if isinstance(value, str):
        return [line.strip(' -•\t') for line in value.splitlines() if line.strip(' -•\t')]
    if isinstance(value, (list, tuple)):
        return [_text(v) for v in value if _text(v)]
    return []


def _from_fields(cls, data):
    names = cls.__dataclass_fields__
    kwargs = {k: _text(v) for k, v in data.items() if k in names}
    item = cls(**kwargs)
    if cls is Scene and not item.id:
        item.id = new_id()
    return item


def bible_from_dict(data):
    bible = StoryBible()
    for name in ('title', 'premise', 'genre', 'style', 'pov', 'tense', 'setting', 'art_style', 'notes'):
        if name in data:
            setattr(bible, name, _text(data[name]))
    if bible.style not in STYLE_PROFILES:
        bible.style = DEFAULT_STYLE
    bible.world_rules = _str_list(data.get('world_rules'))
    bible.outline = _str_list(data.get('outline'))
    bible.characters = [_from_fields(Character, c) for c in data.get('characters') or []
                        if isinstance(c, dict) and _text(c.get('name'))]
    return bible


def save_story(path, state):
    """Atomic JSON write (a crash never leaves half a file)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            json.dump(state.to_dict(), out, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def load_story(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Hikâye dosyası okunamadı: {exc}') from exc
    return StoryState.from_dict(data)


# ============================================================== rendering and context

def estimate_tokens(text):
    return math.ceil(len(text or '') / CHARS_PER_TOKEN)


def render_bible(bible):
    """Deterministic: the same bible always renders to the same bytes (implicit-cache prefix)."""
    lines = ['# HİKÂYE REHBERİ (değişmez gerçekler)']
    for label, value in (('Başlık', bible.title), ('Tür', bible.genre), ('Ana fikir', bible.premise),
                         ('Anlatıcı', bible.pov), ('Anlatı zamanı', bible.tense),
                         ('Üslup', STYLE_PROFILES.get(bible.style, STYLE_PROFILES[DEFAULT_STYLE]).name),
                         ('Mekân ve dönem', bible.setting), ('Görsel üslup (görseller için)', bible.art_style),
                         ('Notlar', bible.notes)):
        if value:
            lines.append(f'{label}: {value}')
    if bible.characters:
        lines.append('\n## Karakterler')
        for c in bible.characters:
            lines.append(f'### {c.name}')
            for label, value in (('Rol', c.role), ('Yaş', c.age), ('Görünüş', c.appearance),
                                 ('Sabit görsel tarif', c.visual), ('Konuşma biçimi', c.voice),
                                 ('İlişkiler', c.relationships), ('Bildikleri', c.knowledge), ('Notlar', c.notes)):
                if value:
                    lines.append(f'- {label}: {value}')
    if bible.world_rules:
        lines.append('\n## Dünyanın kuralları')
        lines.extend(f'- {rule}' for rule in bible.world_rules)
    if bible.outline:
        lines.append('\n## Olay örgüsü taslağı')
        lines.extend(f'{i}. {step}' for i, step in enumerate(bible.outline, 1))
    return '\n'.join(lines)


def render_memory(state):
    blocks = []
    if state.rolling_summary:
        blocks.append('# ŞİMDİYE KADAR OLANLAR (özet)\n' + state.rolling_summary)
    c = state.continuity or {}
    lines = []
    for name, facts in sorted((c.get('knowledge') or {}).items()):
        lines.append(f'- {name} biliyor: ' + '; '.join(facts))
    for name, place in sorted((c.get('locations') or {}).items()):
        lines.append(f'- {name} şu an: {place}')
    for label, key in (('Açık iplik', 'open_threads'), ('Değişen gerçek', 'changed_facts')):
        lines.extend(f'- {label}: {item}' for item in c.get(key) or [])
    if lines:
        blocks.append('# SÜREKLİLİK NOTLARI\n' + '\n'.join(lines))
    return '\n\n'.join(blocks)


def _tail(text, max_chars):
    if len(text) <= max_chars:
        return text
    cut = text[-max_chars:]
    space = cut.find(' ')
    return '[…] ' + (cut[space + 1:] if 0 <= space < 80 else cut)


def build_context(state, *, upto=None, budget_tokens=CONTEXT_BUDGET_TOKENS, recent=RECENT_SCENES):
    """[bible, memory, scenes] parts for the scenes before index ``upto`` (all when None).

    The newest scenes go verbatim, newest first into the budget; one that does not fit is cut from its
    start (its end matters most for continuing). Older scenes appear as their one-line summaries."""
    scenes = state.scenes[:len(state.scenes) if upto is None else max(0, upto)]
    budget = budget_tokens * CHARS_PER_TOKEN
    verbatim = []
    for scene in reversed(scenes[-recent:] if recent else []):
        if not scene.text.strip():
            continue
        if len(scene.text) <= budget:
            verbatim.insert(0, (scene, scene.text))
            budget -= len(scene.text)
        else:
            if not verbatim and budget > 200:
                verbatim.insert(0, (scene, _tail(scene.text, int(budget))))
            break
    shown = {s.id for s, _ in verbatim}
    older = [(i, s) for i, s in enumerate(scenes, 1) if s.id not in shown]
    parts = [render_bible(state.bible)]
    memory = render_memory(state)
    if memory:
        parts.append(memory)
    story = []
    if older:
        story.append('# ÖNCEKİ SAHNELER (kısaca)\n' + '\n'.join(
            f'{i}. {s.title or "Adsız"}: {s.summary or _tail(s.text.strip(), 240)}' for i, s in older))
    if verbatim:
        numbers = {s.id: i for i, s in enumerate(scenes, 1)}
        story.append('# SON SAHNELER (aynen)\n' + '\n\n'.join(
            f'## Sahne {numbers[s.id]}: {s.title or "Adsız"}\n{text}' for s, text in verbatim))
    if story:
        parts.append('\n\n'.join(story))
    return parts


# ============================================================== routing and costs

ROUTES = {
    # task: {quality: (model, thinking level)}
    'bible':   {'draft': ('gemini-3.8-flash', 'medium'), 'final': ('gemini-4-argon', 'high')},
    'outline': {'draft': ('gemini-3.8-flash', 'medium'), 'final': ('gemini-4-argon', 'high')},
    'scene':   {'draft': ('gemini-3.8-flash', 'medium'), 'final': ('gemini-4-argon', 'medium')},
    'rewrite': {'draft': ('gemini-3.8-flash', 'low'),    'final': ('gemini-4-argon', 'high')},
    'memory':  {'draft': ('gemini-3.8-flash', 'low'),    'final': ('gemini-3.8-flash', 'low')},
    'visual':  {'draft': ('gemini-3.8-flash', 'low'),    'final': ('gemini-3.8-flash', 'low')},
    'split':   {'draft': ('gemini-3.8-flash', 'low'),    'final': ('gemini-3.8-flash', 'low')},
}
IMAGE_ROUTES = {'draft': ('gemini-nano-banana-2.1', '1K'), 'final': ('gemini-nano-banana-2.1', '2K'),
                'thumbnail': ('gemini-3.1-flash-lite-image', '1K'), 'premium': ('gemini-3-pro-image', '2K')}
VIDEO_ROUTES = {'preview': ('gemini-omni-1.2-flash', '720p', 6), 'final': ('gemini-omni-1.2-flash', '1080p', 8)}

ROUTING_TABLE = (
    ('Taslak sahne, deneme, devam', 'gemini-3.8-flash', 'medium (hızlı denemede low)', 'Ucuz, hızlı, ücretsiz katmanı var'),
    ('Son okuma, cilalama, karmaşık olay örgüsü', 'gemini-4-argon', 'medium / high', 'Daha tutarlı ve derin; ücretsiz katmanı yok'),
    ('Özet, süreklilik, görsel istemi', 'gemini-3.8-flash (ya da gemini-3.5-flash-lite)', 'low', 'Kısa, yapılandırılmış iş'),
    ('Görsel taslağı', 'gemini-nano-banana-2.1', '1K', '≈0,034 $/görsel'),
    ('Son görsel', 'gemini-nano-banana-2.1', '2K', '≈0,050 $/görsel'),
    ('Hızlı küçük resim', 'gemini-3.1-flash-lite-image', '1K', 'En hızlı/ucuz; çoklu referansta zayıf'),
    ('Premium görsel', 'gemini-3-pro-image', '1K/2K', '≈0,134 $/görsel; yalnızca istenirse'),
    ('Video önizleme', 'gemini-omni-1.2-flash', '720p, 5–8 sn', 'Fiyat belgelenmedi'),
    ('Son video', 'gemini-omni-1.2-flash', '1080p', 'Fiyat belgelenmedi'),
)


def route(task, quality='draft'):
    table = ROUTES.get(task) or ROUTES['scene']
    return table.get(quality) or table['draft']


PRICES_CHECKED = date(2026, 11, 11)
# (valid through date inclusive or None for open-ended, USD per 1M input tokens, USD per 1M output tokens)
TEXT_PRICES = {
    'gemini-3.8-flash': ((date(2026, 12, 31), 0.75, 3.75), (None, 1.50, 7.50)),
    'gemini-4-argon': ((date(2026, 11, 30), 2.00, 10.00), (None, 4.00, 20.00)),
    'gemini-3.5-flash-lite': ((None, 0.30, 2.50),),
}
CACHE_READ_FACTOR = 0.10
IMAGE_PRICES = {  # USD per output image by size
    'gemini-nano-banana-2.1': {'1K': 0.034, '2K': 0.050, '4K': 0.113},
    'gemini-3.1-flash-image': {'1K': 0.067},
    'gemini-3.1-flash-lite-image': {'1K': 0.034},
    'gemini-3-pro-image': {'1K': 0.134, '2K': 0.134},
}
VIDEO_PRICE_NOTE = 'fiyat belgelenmedi'


def text_price(model, on=None):
    on = on or date.today()
    for until, price_in, price_out in TEXT_PRICES.get(model, ()):
        if until is None or on <= until:
            return price_in, price_out
    return None


def estimate_text_cost(model, input_tokens, output_tokens, *, cached_tokens=0, on=None):
    """USD, or None when the model's price is unknown. Output tokens include thinking tokens."""
    price = text_price(model, on)
    if price is None:
        return None
    fresh = max(0, input_tokens - cached_tokens)
    return (fresh * price[0] + cached_tokens * price[0] * CACHE_READ_FACTOR + output_tokens * price[1]) / 1e6


def estimate_image_cost(model, size='1K', count=1):
    per = IMAGE_PRICES.get(model, {}).get(size)
    return None if per is None else per * count


def format_usd(value):
    if value is None:
        return 'fiyat bilinmiyor'
    return f'≈ {value:.4f} $' if value < 0.01 else f'≈ {value:.3f} $'


def image_cost_line(model, size):
    return f'Tahmini maliyet: {format_usd(estimate_image_cost(model, size))} (1 görsel, {model}, {size})'


def video_cost_line(model, resolution, seconds):
    return f'Tahmini maliyet: {VIDEO_PRICE_NOTE} ({model}, {resolution}, {seconds} sn)'


def usage_line(result, on=None):
    """'Token: 1200 girdi (800 önbellek) · 950 çıktı (400 düşünme) · ≈ 0.004 $ · model' for a TextResult."""
    u = result.usage or {}
    output = u.get('output', 0) + u.get('thoughts', 0)
    cost = estimate_text_cost(result.model, u.get('prompt', 0), output, cached_tokens=u.get('cached', 0), on=on)
    line = (f"Token: {u.get('prompt', 0)} girdi" + (f" ({u['cached']} önbellek)" if u.get('cached') else '')
            + f" · {output} çıktı ({u.get('thoughts', 0)} düşünme) · {format_usd(cost)} · {result.model}")
    if getattr(result, 'fell_back', False):
        line += f' (yedek model; {result.fallback_reason})'
    return line


# ============================================================== jobs

@dataclass
class TextJob:
    kind: str
    system_instruction: str
    parts: list
    model: str
    thinking_level: str
    max_output_tokens: int
    scene_id: str = ''
    mode: str = ''
    fallbacks: tuple = None

    def estimated_input_tokens(self):
        return estimate_tokens(self.system_instruction) + sum(estimate_tokens(p) for p in self.parts)


def output_budget(words, thinking_level):
    tokens = int(words * TOKENS_PER_WORD * 1.3) + THINKING_HEADROOM.get(thinking_level, 8192)
    return max(2048, min(gemini_api.MAX_OUTPUT_TOKENS, tokens))


def run_text_job(job, key, *, transport=None, generate=None):
    """Runs a job; a truncated answer that still has text comes back with ``truncated=True``."""
    generate = generate or gemini_api.generate_text
    try:
        return generate(key, job.model, job.parts, system_instruction=job.system_instruction,
                        thinking_level=job.thinking_level, max_output_tokens=job.max_output_tokens,
                        fallbacks=job.fallbacks, transport=transport)
    except ResponseTruncatedError as exc:
        if job.kind in ('scene', 'continue', 'rewrite') and exc.partial.strip():
            return gemini_api.TextResult(exc.partial, job.model, {}, 'MAX_TOKENS', True, job.model)
        raise


def _job(kind, state, parts, task, model, thinking, max_tokens, **extra):
    return TextJob(kind, system_instruction(state.bible.style), parts + [task], model, thinking, max_tokens, **extra)


def _words(text):
    return len(re.findall(r'\w+', text or ''))


def _instruction(text):
    text = (text or '').strip()
    return f'\nYazarın talimatı: {text}' if text else ''


BIBLE_SCHEMA = ('{"title": "", "genre": "", "setting": "", "art_style": "(English: medium, palette, lighting, era)", '
                '"world_rules": [""], "outline": [""], "characters": [{"name": "", "role": "", "age": "", '
                '"appearance": "(Türkçe)", "visual": "(English, fixed: face, hair, build, signature clothing, '
                'colours; 25-45 words)", "voice": "", "relationships": "", "knowledge": "", "notes": ""}]}')


def bible_job(premise, *, style=DEFAULT_STYLE, pov=POV_CHOICES[0], tense=TENSE_CHOICES[0], genre='',
              model=None, quality='draft', characters_hint=''):
    if not (premise or '').strip():
        raise ValueError('Önce hikâyenin ana fikrini yazın.')
    default_model, thinking = route('bible', quality)
    task = ('# GÖREV: Hikâye rehberi oluştur\n'
            f'Ana fikir: {premise.strip()}\n'
            + (f'Tür: {genre}\n' if genre else '') + f'Anlatıcı: {pov}\nAnlatı zamanı: {tense}\n'
            + (f'Karakterler hakkında yazarın notu: {characters_hint}\n' if characters_hint else '')
            + '\nBu fikirden tutarlı bir hikâye rehberi çıkar: 2–5 ana karakter (adları Türkçe ve akılda kalır), '
              'özgül bir mekân ve dönem, 3–6 dünya kuralı, 6–10 adımlık olay örgüsü taslağı. Her karakter için '
              '"visual" alanına görsel tutarlılık için değişmeyecek İngilizce bir tarif yaz. '
              'Yalnızca şu şemada geçerli JSON döndür:\n' + BIBLE_SCHEMA)
    return TextJob('bible', system_instruction(style), [task], model or default_model, thinking, 12000)


def apply_bible(text, base):
    """Merge a generated bible into ``base`` (keeps the author's premise, style, POV and tense)."""
    data = extract_json(text)
    if not isinstance(data, dict):
        raise ValueError('Model geçerli bir hikâye rehberi döndürmedi; tekrar deneyin.')
    generated = bible_from_dict(data)
    for name in ('premise', 'style', 'pov', 'tense'):
        setattr(generated, name, getattr(base, name))
    if base.genre and not generated.genre:
        generated.genre = base.genre
    return generated


def outline_job(state, beats=8, *, model=None, quality='draft', instruction=''):
    default_model, thinking = route('outline', quality)
    task = (f'# GÖREV: Olay örgüsü taslağı\nRehbere ve yazılmış sahnelere uyan {beats} adımlık bir taslak çıkar. '
            'Her adım bir iki cümle: kim neyi istiyor, ne engel oluyor, ne değişiyor. Yazılmış sahneleri baştaki '
            'adımlar olarak koru.' + _instruction(instruction)
            + '\nYalnızca geçerli JSON döndür: {"outline": [""]}')
    return _job('outline', state, build_context(state), task, model or default_model, thinking, 8000)


def apply_outline(text):
    data = extract_json(text)
    steps = _str_list(data.get('outline') if isinstance(data, dict) else data)
    if not steps:
        raise ValueError('Model geçerli bir taslak döndürmedi; tekrar deneyin.')
    return steps


def next_scene_job(state, *, instruction='', words=DEFAULT_SCENE_WORDS, model=None, quality='draft'):
    default_model, thinking = route('scene', quality)
    number = len(state.scenes) + 1
    outline = state.bible.outline
    step = f'\nTaslaktaki ilgili adım: {outline[number - 1]}' if 0 < number <= len(outline) else ''
    start = ('Önceki sahnenin bittiği yerden sonra gelen anı yaz; sahne geçişi doğal olsun.' if state.scenes
             else 'Hikâyenin açılış sahnesini yaz: okuru ilk cümleden bir karakterin içine ve bir duruma yerleştir.')
    task = (f'# GÖREV: {number}. sahneyi yaz\nHedef uzunluk: yaklaşık {words} kelime.{step}{_instruction(instruction)}\n'
            f'{start} Yalnızca sahne metnini yaz; başlık, açıklama ya da not ekleme.')
    return _job('scene', state, build_context(state), task, model or default_model, thinking,
                output_budget(words, thinking))


def continue_job(state, scene_id, *, instruction='', words=400, model=None, quality='draft'):
    index = state.index_of(scene_id)
    if index < 0:
        raise ValueError('Sahne bulunamadı.')
    scene = state.scenes[index]
    if not scene.text.strip():
        raise ValueError('Devam edilecek metin yok; önce sahneyi yazın.')
    default_model, thinking = route('scene', quality)
    last = _tail(scene.text.strip(), 400)
    task = (f'# GÖREV: {index + 1}. sahneye devam et\nYukarıdaki "Sahne {index + 1}" metni şu sözlerle bitiyor:\n'
            f'"""{last}"""\nTam bu noktadan, yeni bir paragrafla, kesintisiz devam et. Yaklaşık {words} kelime.'
            f'{_instruction(instruction)}\nÖnceki metni tekrar etme ya da özetleme; yalnızca yeni metni yaz.')
    return _job('continue', state, build_context(state, upto=index + 1), task, model or default_model, thinking,
                output_budget(words, thinking), scene_id=scene_id)


REWRITE_MODES = {
    'rewrite': ('yeniden yaz', 1.0, 'Aynı olayları koru, anlatımı güçlendir.'),
    'extend': ('genişlet', 1.5, 'Olayları koru; atlanan anları sahnele, diyalog ve ayrıntıyla derinleştir.'),
    'shorten': ('kısalt', 0.6, 'Olayları ve önemli replikleri koru; tekrarları, gereksiz betimlemeyi ve açıklamayı at.'),
}


def rewrite_job(state, scene_id, mode='rewrite', *, instruction='', model=None, quality='draft'):
    if mode not in REWRITE_MODES:
        raise ValueError(f'Bilinmeyen yeniden yazma biçimi: {mode}')
    index = state.index_of(scene_id)
    if index < 0:
        raise ValueError('Sahne bulunamadı.')
    scene = state.scenes[index]
    if not scene.text.strip():
        raise ValueError('Yeniden yazılacak metin yok.')
    label, factor, how = REWRITE_MODES[mode]
    words = max(80, int(_words(scene.text) * factor))
    default_model, thinking = route('rewrite', quality)
    following = state.scenes[index + 1:]
    after = ('\nSonraki sahneler bu sahnenin sonucuna dayanıyor; sonunda varılan durumu değiştirme.' if following else '')
    task = (f'# GÖREV: {index + 1}. sahneyi {label}\n{how} Hedef uzunluk: yaklaşık {words} kelime.{after}'
            f'{_instruction(instruction)}\nYalnızca yeni sahne metnini yaz.\n\n## Mevcut metin\n{scene.text.strip()}')
    return _job('rewrite', state, build_context(state, upto=index), task, model or default_model, thinking,
                output_budget(words, thinking), scene_id=scene_id, mode=mode)


def clean_prose(text):
    """Drop wrappers models sometimes add despite instructions: code fences, 'Sahne 3:' headings."""
    text = (text or '').strip()
    text = re.sub(r'^```[a-zA-Z]*\n|\n```$', '', text).strip()
    text = re.sub(r'^(#+\s*)?(Sahne|Bölüm)\s*\d+\s*[:.\-–—][^\n]*\n+', '', text, flags=re.I)
    return text.strip()


def apply_scene_text(state, job, text):
    """Applies a scene/continue/rewrite answer; returns the scene."""
    text = clean_prose(text)
    if job.kind == 'scene':
        scene = Scene(title=f'Sahne {len(state.scenes) + 1}', text=text)
        state.scenes.append(scene)
        return scene
    scene = state.scene(job.scene_id)
    if scene is None:
        raise ValueError('Sahne artık yok.')
    scene.text = scene.text.rstrip() + '\n\n' + text if job.kind == 'continue' else text
    return scene


# ---------------------------------------------------------------- splitting

def paragraphs(text):
    return [p.strip() for p in re.split(r'\n\s*\n', (text or '').strip()) if p.strip()]


def split_job(state, text, *, model=None):
    paras = paragraphs(text)
    if len(paras) < 2:
        raise ValueError('Bölünecek metin en az iki paragraf olmalı.')
    default_model, thinking = route('split')
    numbered = '\n\n'.join(f'[{i}] {p[:600]}' for i, p in enumerate(paras, 1))
    task = ('# GÖREV: Metni sahnelere böl\nAşağıdaki paragraflar numaralı. Mekân, zaman ya da bakış açısı değişen '
            'yerlerde yeni sahne başlat. Her sahne için başladığı paragraf numarasını ve kısa bir Türkçe başlık ver. '
            'İlk sahne 1. paragrafta başlar. Yalnızca geçerli JSON döndür: {"scenes": [{"start": 1, "title": ""}]}'
            f'\n\n{numbered}')
    return TextJob('split', system_instruction(state.bible.style), [render_bible(state.bible), task],
                   model or default_model, thinking, 4096)


def fallback_split(text):
    """Without a model: split on scene-break lines (***, * * *, ---, #) or keep one scene."""
    chunks = [c.strip() for c in re.split(r'\n\s*(?:\*\s*\*\s*\*|-{3,}|#{1,3}[^\n]*)\s*\n', '\n' + (text or '') + '\n')]
    return [Scene(title=f'Sahne {i}', text=c) for i, c in enumerate((c for c in chunks if c), 1)]


def apply_split(text, source):
    """Scenes from the model's start indices; any malformed answer falls back to ``fallback_split``."""
    paras = paragraphs(source)
    data = extract_json(text)
    items = data.get('scenes') if isinstance(data, dict) else data
    starts = []
    for item in items if isinstance(items, list) else []:
        try:
            start = int(item.get('start'))
        except (AttributeError, TypeError, ValueError):
            continue
        if 1 <= start <= len(paras) and start not in [s for s, _ in starts]:
            starts.append((start, _text(item.get('title'))))
    starts.sort()
    if not starts:
        return fallback_split(source)
    if starts[0][0] != 1:
        starts.insert(0, (1, ''))
    scenes = []
    for n, (start, title) in enumerate(starts):
        end = starts[n + 1][0] - 1 if n + 1 < len(starts) else len(paras)
        scenes.append(Scene(title=title or f'Sahne {n + 1}', text='\n\n'.join(paras[start - 1:end])))
    return scenes


# ---------------------------------------------------------------- memory

MEMORY_SCHEMA = ('{"scene_summary": "(2-3 cümle)", "rolling_summary": "(tüm hikâye, en fazla 250 kelime)", '
                 '"continuity": {"knowledge": {"Ad": ["bildiği önemli bilgi"]}, "locations": {"Ad": "şu an nerede, '
                 'hangi durumda"}, "open_threads": [""], "changed_facts": [""]}}')


def memory_job(state, scene_id, *, model=None):
    index = state.index_of(scene_id)
    if index < 0:
        raise ValueError('Sahne bulunamadı.')
    scene = state.scenes[index]
    default_model, thinking = route('memory')
    parts = [render_bible(state.bible)]
    memory = render_memory(state)
    if memory:
        parts.append(memory)
    task = (f'# GÖREV: Hafızayı güncelle\n{index + 1}. sahne yazıldı (aşağıda). Önceki özeti ve süreklilik notlarını '
            'bu sahneyle güncelle: özet tüm hikâyeyi kapsasın; notlarda her karakterin bildiklerini, nerede '
            'olduğunu, açık iplikleri ve rehbere göre değişen gerçekleri tut. Artık geçerli olmayanı çıkar. '
            f'Yalnızca geçerli JSON döndür:\n{MEMORY_SCHEMA}\n\n## Sahne {index + 1}: {scene.title}\n{scene.text}')
    return TextJob('memory', system_instruction(state.bible.style), parts + [task], model or default_model,
                   thinking, 6000, scene_id=scene_id)


def _continuity(data):
    """Validated continuity sheet; anything malformed is dropped, never raised."""
    if not isinstance(data, dict):
        return {}
    result = {}
    knowledge = data.get('knowledge')
    if isinstance(knowledge, dict):
        result['knowledge'] = {_text(k): _str_list(v) for k, v in knowledge.items() if _text(k) and _str_list(v)}
    locations = data.get('locations')
    if isinstance(locations, dict):
        result['locations'] = {_text(k): _text(v) for k, v in locations.items() if _text(k) and _text(v)}
    for key in ('open_threads', 'changed_facts'):
        if key in data:
            result[key] = _str_list(data.get(key))
    return result


def apply_memory(state, scene_id, text):
    """Update summary + continuity from the model's JSON. Returns False (state untouched) on bad JSON;
    valid fields are applied even when others are malformed."""
    data = extract_json(text)
    if not isinstance(data, dict):
        return False
    changed = False
    scene = state.scene(scene_id)
    summary = data.get('scene_summary')
    if scene is not None and isinstance(summary, str) and summary.strip():
        scene.summary = summary.strip()
        changed = True
    rolling = data.get('rolling_summary')
    if isinstance(rolling, str) and rolling.strip():
        state.rolling_summary = rolling.strip()
        changed = True
    if isinstance(data.get('continuity'), dict):
        sheet = _continuity(data['continuity'])
        if sheet:
            merged = dict(state.continuity)
            merged.update(sheet)
            state.continuity = merged
            changed = True
    return changed


# ---------------------------------------------------------------- visual prompts

VISUAL_SCHEMA = ('{"characters": ["(bu karede görünen rehber karakterlerinin adları)"], "subject": "", "setting": "", '
                 '"lighting": "", "composition": "(lens, shot size, angle)", "image_prompt": "(English, 40-90 words, '
                 'one decisive moment)", "motion_prompt": "(English, 1-3 sentences: camera move, subject action, '
                 'ambience and sound)"}')


def visual_job(state, scene_id, *, model=None):
    scene = state.scene(scene_id)
    if scene is None or not scene.text.strip():
        raise ValueError('Görsel istemi için önce sahne metni gerekli.')
    default_model, thinking = route('visual')
    task = ('# GÖREV: Görsel ve hareket istemi\nAşağıdaki sahnenin en güçlü, tek bir anını seç ve İngilizce bir görsel '
            'istemi yaz: özne ve eylem, mekân, ışık, lens/kompozisyon, üslup. Karakterlerin görünüşünü rehberdeki '
            '"Sabit görsel tarif"ten al, değiştirme. Ne istendiğini tarif et, ne istenmediğini değil. Sonra aynı an '
            'için kısa bir video hareket istemi yaz. Yalnızca geçerli JSON döndür:\n'
            f'{VISUAL_SCHEMA}\n\n## Sahne: {scene.title}\n{scene.text}')
    return TextJob('visual', system_instruction(state.bible.style), [render_bible(state.bible), task],
                   model or default_model, thinking, 4096, scene_id=scene_id)


def characters_in(bible, text, names=()):
    """Bible characters named in ``names`` or mentioned in ``text`` (first name match is enough), bible order."""
    wanted = {n.strip().casefold() for n in names if isinstance(n, str) and n.strip()}
    lowered = (text or '').casefold()
    found = []
    for c in bible.characters:
        full = c.name.casefold()
        first = full.split()[0] if full.split() else full
        if full in wanted or first in wanted or (first and re.search(r'(?<!\w)' + re.escape(first), lowered)):
            found.append(c)
    return found


def compose_image_prompt(bible, core, characters):
    """Final English image prompt: the scene moment, each character's fixed visual description verbatim,
    and the bible's art style."""
    lines = [core.strip().rstrip('.') + '.']
    described = [c for c in characters if c.visual.strip()]
    if described:
        lines.append('Characters (keep exactly as described): ' + ' '.join(
            f'{c.name}: {c.visual.strip().rstrip(".")}.' for c in described))
    if bible.art_style.strip():
        lines.append(f'Art style: {bible.art_style.strip().rstrip(".")}.')
    lines.append('A clean cinematic frame with the scene only, no lettering.')
    return '\n'.join(lines)


def compose_motion_prompt(data):
    motion = _text(data.get('motion_prompt')) if isinstance(data, dict) else ''
    if not motion:
        motion = 'Slow push-in on the main subject; subtle natural movement in the scene; quiet ambient sound.'
    if not re.search(r'sound|audio|ambien|music|silence|noise|voice', motion, re.I):
        motion = motion.rstrip('.') + '. Natural ambient sound of the setting.'
    return motion


def apply_visual(state, scene_id, text):
    """Fill the scene's visual and motion prompts; returns the scene. Falls back to a local prompt."""
    scene = state.scene(scene_id)
    if scene is None:
        raise ValueError('Sahne artık yok.')
    data = extract_json(text)
    if not isinstance(data, dict) or not _text(data.get('image_prompt')):
        scene.visual_prompt, scene.motion_prompt = fallback_visual_prompt(state.bible, scene)
        return scene
    names = data.get('characters') if isinstance(data.get('characters'), list) else []
    core = _text(data.get('image_prompt'))
    scene.visual_prompt = compose_image_prompt(state.bible, core, characters_in(state.bible, scene.text, names))
    scene.motion_prompt = compose_motion_prompt(data)
    return scene


def fallback_visual_prompt(bible, scene):
    """Without a model call: a usable prompt from the scene's summary/opening (not translated)."""
    basis = scene.summary or ' '.join(re.split(r'(?<=[.!?…])\s+', scene.text.strip())[:3])
    core = f'A key moment from a {bible.genre or "dramatic"} story, scene "{scene.title}": {basis[:400]}'
    return (compose_image_prompt(bible, core, characters_in(bible, scene.text)),
            compose_motion_prompt({}))


def video_prompt(scene, from_image):
    """Image-to-video: the motion prompt alone (the image carries the look). Text-to-video: both."""
    motion = scene.motion_prompt or compose_motion_prompt({})
    if from_image:
        return motion
    return f'{scene.visual_prompt.strip()}\nMotion and sound: {motion}'


# ============================================================== files and JSON

def extract_json(text):
    """The first JSON object/array in a model answer (code fences and chatter tolerated), or None."""
    if not isinstance(text, str):
        return None
    cleaned = re.sub(r'```(?:json)?', '', text).strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass
    for opener, closer in (('{', '}'), ('[', ']')):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if 0 <= start < end:
            try:
                return json.loads(cleaned[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                continue
    return None


def slug(text, fallback='hikaye'):
    table = str.maketrans('çğıöşüâîûÇĞİÖŞÜÂÎÛ', 'cgiosuaiuCGIOSUAIU')
    value = re.sub(r'[^A-Za-z0-9]+', '-', (text or '').translate(table)).strip('-').lower()
    return value[:40] or fallback


def media_path(folder, state, scene, kind, extension):
    """Stable, non-overwriting name: <folder>/<story-slug>/sahne-03-<id>-gorsel.png (then -2, -3…)."""
    number = state.index_of(scene.id) + 1
    base = Path(folder) / slug(state.bible.title)
    base.mkdir(parents=True, exist_ok=True)
    stem = f'sahne-{number:02d}-{scene.id}-{kind}'
    candidate = base / f'{stem}{extension}'
    counter = 2
    while candidate.exists():
        candidate = base / f'{stem}-{counter}{extension}'
        counter += 1
    return candidate
