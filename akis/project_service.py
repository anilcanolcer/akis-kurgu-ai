"""Versioned project document validation and atomic persistence."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from akis.timeline_model import Timeline

CURRENT_VERSION = 2


def migrate(document):
    if document.get('format') != 'akis-kurgu-project':
        raise ValueError('Unsupported project format')
    version = document.get('version', 1)
    if not isinstance(version, int) or version < 1 or version > CURRENT_VERSION:
        raise ValueError('Unsupported project version')
    result = dict(document)
    if version == 1:
        result['timeline'] = result.get('timeline') or Timeline.from_legacy(result.get('state', {})).to_dict()
    Timeline.from_dict(result['timeline'])
    result['version'] = CURRENT_VERSION
    return result


def load(path):
    with Path(path).open(encoding='utf-8') as stream:
        return migrate(json.load(stream))


def save(path, document):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = migrate(document)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                         prefix=target.name + '.', suffix='.tmp', delete=False) as stream:
            name = stream.name
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def make_document(state, timeline, publish, ai_prompt):
    return {
        'format': 'akis-kurgu-project',
        'version': CURRENT_VERSION,
        'saved_at': datetime.now().astimezone().isoformat(),
        'state': dict(state),
        'timeline': timeline.to_dict(),
        'publish': dict(publish),
        'ai_prompt': ai_prompt,
    }


def save_with_snapshot(path, document, snapshot=False):
    target = Path(path)
    save(target, document)
    if snapshot:
        versions = target.parent / f'{target.name}.versions'
        versions.mkdir(exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        save(versions / f'{stamp}.json', document)


def load_with_source(path):
    document = load(path)
    source = document.get('state', {}).get('source', '')
    source_path = Path(source)
    if source and not source_path.is_absolute():
        source_path = (Path(path).parent / source_path).resolve()
        document.setdefault('state', {})['source'] = str(source_path)
    if not source or not source_path.exists():
        raise FileNotFoundError('Projede kullanılan kaynak video bulunamadı.')
    return document, str(source_path)
