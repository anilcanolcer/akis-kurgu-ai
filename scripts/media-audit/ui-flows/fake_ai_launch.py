"""Start the editor with the AI service replaced by a fixed reply, for the real-UI AI flow.

Nothing leaves the computer and the Windows credential store is never read or written: post_json answers
every request with the text in the file FAKE_AI_REPLY (as an OpenAI Responses reply), and each request's prompt
and number of pictures are appended to FAKE_AI_LOG.
Usage: python fake_ai_launch.py   (environment: FAKE_AI_REPLY, FAKE_AI_LOG; run from the project folder)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from akis import ai_providers  # noqa: E402


def fake_post(provider, url, body, headers, timeout, **_):
    if isinstance(body, (bytes, bytearray)):       # the request as it would go out: JSON bytes
        body = json.loads(body)
    pictures = sum(1 for message in body.get('input', []) for part in message.get('content', [])
                   if part.get('type') == 'input_image')
    texts = [part.get('text', '') for message in body.get('input', []) for part in message.get('content', [])
             if part.get('type') == 'input_text']
    with open(os.environ['FAKE_AI_LOG'], 'a', encoding='utf-8') as log:
        log.write(json.dumps({'provider': provider, 'url': url, 'model': body.get('model'), 'pictures': pictures,
                              'prompt': texts[0][:4000] if texts else ''}, ensure_ascii=False) + '\n')
    reply = Path(os.environ['FAKE_AI_REPLY']).read_text(encoding='utf-8')   # read each time: a flow can change it
    return {'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': reply}]}]}


ai_providers.post_json = fake_post
ai_providers.load_key = lambda service, provider: ''
ai_providers.save_key = lambda service, provider, key: None
ai_providers.delete_key = lambda service, provider: None

import main  # noqa: E402

raise SystemExit(main.main())
