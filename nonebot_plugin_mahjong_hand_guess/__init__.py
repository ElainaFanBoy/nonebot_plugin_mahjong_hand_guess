from pathlib import Path

from nonebot.adapters import Event
from nonebot.plugin import PluginMetadata, require, inherit_supported_adapters

from .handler import HandGuess
from .imghandler import image_save

require("nonebot_plugin_alconna")
require("nonebot_plugin_waiter")

from nonebot_plugin_waiter import waiter
from nonebot_plugin_alconna import UniMsg, Command, MsgTarget, UniMessage

__plugin_meta__ = PluginMetadata(
    name="日麻猜手牌小游戏",
    description="日麻猜手牌小游戏",
    usage="根据提示猜出手牌",
    type="application",
    homepage="https://github.com/ElainaFanBoy/nonebot_plugin_majhong_hand_guess",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={
        "unique_name": "mahjong-hand-guess",
        "author": "Nanako <demo0929@vip.qq.com>",
        "version": "0.1.1",
    },
)

sv = (
    Command("麻将猜手牌", "日麻猜手牌小游戏")
    .alias("猜手牌")
    .usage("根据提示猜出手牌")
    .build(use_cmd_start=True, auto_send_output=True, block=True, priority=16)
)

__dir = Path(__file__).parent


@sv.handle()
async def main(event: Event, target: MsgTarget):
    if target.private:
        await sv.finish("请在群聊中使用")

    hg = HandGuess(event.get_user_id(), target.id)
    if hg.already_start():
        await sv.finish("游戏已经开始了, 请不要重复开始")
    hg.start()
    await sv.send(f"开始一轮猜手牌, 每个人有{hg.MAX_GUESS}次机会")

    rule_path = __dir.joinpath("assets", "rule.png")
    await sv.send(UniMessage.image(path=rule_path))

    @waiter(waits=["message"], block=False)
    async def listen(msg: UniMsg):
        res = await hg.guesses_handler(msg.extract_plain_text())
        if not res:
            return
        if res["img"]:
            await UniMessage.image(raw=image_save(res["img"])).send(at_sender=True)
        if res["msg"]:
            await UniMessage.text(res["msg"]).send(at_sender=True)
        if res["finish"]:
            return True

    resp = await listen.wait(timeout=hg.TIMEOUT)
    if resp is None:
        await sv.send("游戏已超时, 请重新开始")
        res = await hg.timeout()
        if res and res["img"]:
            await UniMessage.image(raw=image_save(res["img"])).send(at_sender=True)
        if res and res["msg"]:
            await UniMessage.text(res["msg"]).send(at_sender=True)
    await sv.finish()
