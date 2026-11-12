"""Бот моста эфира с Discord (discord.py). Логика в air/bridge.py; здесь подключение, очередь и сообщения канала.

Запуск: сам вместе с сайтом (поток в процессе сервера, см. start_in_background) или командой manage.py air_bridge.
Нужен DISCORD_BOT_TOKEN. Подключается только тот процесс, который держит аренду моста.
"""
import asyncio
import logging
import threading

from asgiref.sync import sync_to_async

from air import bridge

log = logging.getLogger("air.bridge")
PUMP = 2            # секунд между проходами очереди
_started = threading.Event()


def _client_class():
    import discord

    class Bridge(discord.Client):
        def __init__(self, holder):
            intents = discord.Intents.default()
            intents.message_content = True
            super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
            self.holder = holder

        async def setup_hook(self):
            self.loop.create_task(self.pump())

        async def on_ready(self):
            log.info("air bridge: connected as %s", self.user)
            await sync_to_async(bridge.lease)(self.holder, str(self.user))

        async def on_message(self, message):
            if message.author.bot or message.webhook_id or not message.content.strip():
                return
            made, reason = await sync_to_async(bridge.inbound)(message.channel.id, message.author.id, message.content, message.id)
            if made is None and reason != "no bridge":
                try:
                    await message.add_reaction("⛔")
                    await message.reply(f"не в эфире: {reason}", delete_after=20, mention_author=False)
                except discord.HTTPException:
                    pass

        async def pump(self):
            await self.wait_until_ready()
            beat = 0
            while not self.is_closed():
                try:
                    await self.send_out()
                    await self.delete_hidden()
                    beat += PUMP
                    if beat >= bridge.BEAT:
                        beat = 0
                        if not await sync_to_async(bridge.lease)(self.holder, str(self.user)):
                            log.warning("air bridge: lease taken by another process, disconnecting")
                            await self.close()
                            return
                except Exception as error:                      # noqa: BLE001 — бот не падает из-за одного сбоя
                    log.exception("air bridge pump: %s", error)
                await asyncio.sleep(PUMP)

        async def channel(self, channel_id):
            found = self.get_channel(int(channel_id))
            return found or await self.fetch_channel(int(channel_id))

        async def send_out(self):
            for message_id, channel_id, text in await sync_to_async(bridge.outbox)():
                try:
                    posted = await (await self.channel(channel_id)).send(discord.utils.escape_mentions(text))
                    await sync_to_async(bridge.sent)(message_id, posted.id)
                except (discord.HTTPException, ValueError) as error:
                    await sync_to_async(bridge.failed)(message_id, error)

        async def delete_hidden(self):
            for message_id, channel_id, discord_id in await sync_to_async(bridge.to_delete)():
                try:
                    found = await (await self.channel(channel_id)).fetch_message(int(discord_id))
                    await found.delete()
                except discord.NotFound:
                    pass
                except (discord.HTTPException, ValueError) as error:
                    await sync_to_async(bridge.failed)(message_id, error)
                    continue
                await sync_to_async(bridge.deleted)(message_id)

    return Bridge


def run(stop_on_lease_loss=False):
    """Держать мост, пока процесс жив: ждать аренду, подключаться, переподключаться после сбоев."""
    import time

    import discord

    token = bridge.token()
    if not token:
        log.warning("air bridge: DISCORD_BOT_TOKEN is not set")
        return
    holder = bridge.holder_name()
    Bridge = _client_class()
    while True:
        if not bridge.lease(holder):
            time.sleep(bridge.BEAT)                         # мост держит другой процесс
            continue
        client = Bridge(holder)
        try:
            client.run(token, log_handler=None)
        except discord.LoginFailure as error:
            bridge.lease(holder, error=f"токен не подошёл: {error}")
            bridge.release(holder)
            log.error("air bridge: bad token: %s", error)
            return
        except Exception as error:                          # noqa: BLE001
            bridge.lease(holder, error=str(error))
            log.exception("air bridge stopped: %s", error)
        finally:
            bridge.release(holder)
        if stop_on_lease_loss:
            return
        time.sleep(bridge.BEAT)


def start_in_background():
    """Поток с ботом в процессе сайта (один раз на процесс). Без токена ничего не делает."""
    import time

    if not bridge.token() or _started.is_set():
        return
    _started.set()

    def later():
        time.sleep(5)                                       # дать сайту подняться: приложения, база
        run()

    threading.Thread(target=later, name="air-bridge", daemon=True).start()
