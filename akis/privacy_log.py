"""What has left this computer since the app started, in plain words.

The app works locally; things are sent out only when the user starts an AI step or an update check. Each
place that sends something records it here (who received it, what kind of thing), and the sidebar shows
the list. Nothing else is stored: no contents, no times, and the list is gone when the app closes.
"""
import threading

# kind -> Turkish description (translated by the caller's `say`)
KINDS = {
    'frames': 'video kareleri ve istek metni',
    'text': 'istek metni',
    'audio': 'videonun sesi',
    'story': 'hikâye metni ve görselleri',
    'update': 'sürüm denetimi (video gönderilmez)',
}
NOTHING = 'Bu oturumda bilgisayarınızdan hiçbir şey gönderilmedi.'
HEADING = 'Bu oturumda gönderilenler:'

_lock = threading.Lock()
_sent = []  # (receiver, kind), each pair once, in the order first seen


def note(receiver, kind):
    """Record that `kind` of data was sent to `receiver`. Safe from any thread; never raises."""
    if kind not in KINDS or not receiver:
        return
    with _lock:
        if (receiver, kind) not in _sent:
            _sent.append((str(receiver), kind))


def sent():
    with _lock:
        return list(_sent)


def clear():
    with _lock:
        _sent.clear()


def summary(say=str):
    """The sidebar text. `say` translates a Turkish string (the default leaves it Turkish)."""
    items = sent()
    if not items:
        return say(NOTHING)
    receivers = []
    for receiver, _ in items:
        if receiver not in receivers:
            receivers.append(receiver)
    lines = [f'• {receiver}: ' + ', '.join(say(KINDS[kind]) for who, kind in items if who == receiver)
             for receiver in receivers]
    return say(HEADING) + '\n' + '\n'.join(lines)
