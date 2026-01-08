from pathlib import Path

from nonebot.adapters import Event
from nonebot.plugin import PluginMetadata, require, inherit_supported_adapters

from .handler import HandGuess
from .imghandler import image_save

require("nonebot_plugin_session")
require("nonebot_plugin_alconna")
require("nonebot_plugin_waiter")

from nonebot_plugin_session import EventSession, SessionIdType
from nonebot_plugin_alconna import UniMsg, Command, UniMessage, MsgTarget
from nonebot_plugin_waiter import waiter

__plugin_meta__ = PluginMetadata(
    name="日麻猜手牌小游戏",
    description="日麻猜手牌小游戏",
    usage="根据提示猜出手牌",
    type="application",
    homepage="https://github.com/ElainaFanBoy/nonebot_plugin_mahjong_hand_guess",
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna", "nonebot_plugin_session"),
    extra={
        "unique_name": "mahjong-hand-guess",
        "author": "Nanako <demo0929@vip.qq.com>",
        "version": "0.5.0",
    },
)

sv = (
    Command("麻将猜手牌", "日麻猜手牌小游戏")
    .config(fuzzy_match=False)
    .shortcut("猜手牌", {"fuzzy": False, "prefix": True})
    .usage("根据提示猜出手牌")
    .build(use_cmd_start=True, auto_send_output=True, block=True, priority=16)
)

__dir = Path(__file__).parent


@sv.handle()
async def main(event: Event, target: MsgTarget, session: EventSession):
    if target.private:
        await sv.finish("请在群聊中使用")
    session_id = session.get_id(SessionIdType.GROUP)
    hg = HandGuess(event.get_user_id(), session_id)
    if hg.already_start():
        await sv.finish("游戏已经开始了, 请不要重复开始")
    hg.start()
    await sv.send(f"开始一轮猜手牌, 每个人有{hg.MAX_GUESS}次机会\n输入 “取消” 结束游戏")

    rule_path = __dir.joinpath("assets", "rule.png")
    with open(rule_path, "rb") as f:
        pic = f.read()
    await sv.send(UniMessage.image(raw=pic))

    @waiter(waits=["message"], block=False)
    async def listen(msg: UniMsg, _session: EventSession):
        if _session.get_id(SessionIdType.GROUP) != session_id:
            return
        text = msg.extract_plain_text()
        if text == "取消":
            return False
        res = await hg.guesses_handler(text)
        if not res:
            return
        if res["img"]:
            await UniMessage.image(raw=image_save(res["img"])).send(at_sender=True)
        if res["msg"]:
            await UniMessage.text(res["msg"]).send(at_sender=True)
        if res["finish"]:
            return True

    resp = await listen.wait(timeout=hg.TIMEOUT)
    if not resp:
        if resp is None:
            await sv.send("游戏已超时, 请重新开始")
        else:
            await sv.send("游戏已取消")
        res = await hg.timeout()
        if res and res["img"]:
            await UniMessage.image(raw=image_save(res["img"])).send(at_sender=True)
        if res and res["msg"]:
            await UniMessage.text(res["msg"]).send(at_sender=True)
    await sv.finish()
