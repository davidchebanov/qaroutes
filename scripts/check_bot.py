"""Offline checks: real PTB concurrency and RetryAfter, no Telegram requests."""
import ast
import asyncio
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.error import RetryAfter
from telegram.ext import AIORateLimiter, Application, CallbackQueryHandler, CommandHandler, ContextTypes


async def main():
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'bot.py').read_text())
    # Load only definitions: do not start the HTTP server, self-ping or polling.
    definitions = ast.Module(body=[n for n in tree.body if isinstance(
        n, (ast.FunctionDef, ast.AsyncFunctionDef))], type_ignores=[])
    scope = dict(globals(), BOT_TOKEN='123456:offline-test-token',
                 WEBAPP_URL='https://example.com', SELF_URL='https://example.onrender.com', CHANNEL='@qaroutes')
    exec(compile(definitions, 'bot.py', 'exec'), scope)
    app = scope['build_application']()
    for status, expected in [('member', True), ('administrator', True),
                             ('creator', True), ('left', False), ('kicked', False)]:
        assert scope['subscribed'](SimpleNamespace(status=status)) == expected
    for value in (True, False):
        assert scope['subscribed'](SimpleNamespace(status='restricted', is_member=value)) == value

    fields = {'user': json.dumps({'id': 123}), 'auth_date': str(int(time.time()))}
    def sign(values):
        secret = hmac.new(b'WebAppData', scope['BOT_TOKEN'].encode(), hashlib.sha256).digest()
        check = '\n'.join(f'{k}={v}' for k, v in sorted(values.items()))
        return urlencode(dict(values, hash=hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()))
    assert scope['verified_user'](sign(fields)) == 123
    for data in (sign(fields).replace('123', '456'), sign(dict(fields, auth_date='1'))):
        try:
            scope['verified_user'](data)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid session accepted')

    for status in ('member', 'left', 'kicked', 'error'):
        reply = AsyncMock()
        update = SimpleNamespace(callback_query=None, effective_user=SimpleNamespace(id=123),
                                 effective_message=SimpleNamespace(reply_text=reply))
        lookup = AsyncMock(return_value=SimpleNamespace(status=status))
        if status == 'error':
            lookup.side_effect = RuntimeError('Telegram unavailable')
        await scope['start'](update, SimpleNamespace(bot=SimpleNamespace(get_chat_member=lookup)))
        kwargs = reply.call_args.kwargs
        keyboard = kwargs.get('reply_markup')
        has_app = keyboard and any(b.web_app for row in keyboard.inline_keyboard for b in row)
        assert bool(has_app) == (status == 'member')
    assert app.concurrent_updates == 8
    assert {c for h in app.handlers[0] if isinstance(h, CommandHandler) for c in h.commands} == {'start', 'help'}
    active = peak = completed = 0

    async def work():
        nonlocal active, peak, completed
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        completed += 1

    await asyncio.gather(*(app.update_processor.process_update(None, work())
                           for _ in range(32)))
    assert peak == 8 and completed == 32, (peak, completed)

    calls = 0
    async def limited_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RetryAfter(0)
        return 'sent'

    limiter = app.bot.rate_limiter
    result = await limiter.process_request(limited_once, (), {}, 'sendMessage',
                                           {'chat_id': 123}, None)
    assert result == 'sent' and calls == 2

    calls = 0
    async def always_limited():
        nonlocal calls
        calls += 1
        raise RetryAfter(0)

    try:
        await limiter.process_request(always_limited, (), {}, 'sendMessage',
                                      {'chat_id': 123}, None)
    except RetryAfter:
        assert calls == 4, calls
    else:
        raise AssertionError('Retry limit was not enforced')
    print('PASS: membership statuses, signed sessions, expired/tampered sessions, start denial on unsubscribe/API error; concurrency 8 and bounded retries')


if __name__ == '__main__':
    asyncio.run(main())
