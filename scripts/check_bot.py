"""Offline checks: real PTB concurrency and RetryAfter, no Telegram requests."""
import ast
import asyncio
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.error import RetryAfter
from telegram.ext import AIORateLimiter, Application, CommandHandler, ContextTypes


async def main():
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'bot.py').read_text())
    # Load only definitions: do not start the HTTP server, self-ping or polling.
    definitions = ast.Module(body=[n for n in tree.body if isinstance(
        n, (ast.FunctionDef, ast.AsyncFunctionDef))], type_ignores=[])
    scope = dict(globals(), BOT_TOKEN='123456:offline-test-token',
                 WEBAPP_URL='https://example.com')
    exec(compile(definitions, 'bot.py', 'exec'), scope)
    app = scope['build_application']()
    assert app.concurrent_updates == 8
    assert {c for h in app.handlers[0] for c in h.commands} == {'start', 'help'}
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
    print('PASS: 32 commands completed; peak concurrency 8; RetryAfter retried; retries bounded at 3')


if __name__ == '__main__':
    asyncio.run(main())
