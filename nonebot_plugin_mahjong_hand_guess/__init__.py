from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot import on_command, on_message
from .handler import HandGuess
from .utils import get_path

sv = on_command("麻将猜手牌", aliases={"猜手牌"}, priority=16, block=True)


@sv.handle()
async def main(bot: Bot, event: MessageEvent):
    user_id = event.user_id
    group_id = event.group_id

    hg = HandGuess(user_id, group_id)
    res = await hg.start()
    if res["error"]:
        await sv.finish(res["msg"])
    await sv.send(f"开始一轮猜手牌, 每个人有{hg.MAX_GUESS}次机会")

    rule_path = get_path("assets", "rule.png")
    await sv.send(MessageSegment.image(f"file:///{rule_path}"))

group_message = on_message(priority=17, block=False)


@group_message.handle()
async def on_input_chara_name(bot: Bot, event: MessageEvent):
    msg = event.raw_message
    user_id = event.user_id
    group_id = event.group_id

    hg = HandGuess(user_id, group_id)

    if hg.is_start():
        res = await hg.guesses_handler(msg)
        if res.get("img"):
            await group_message.send(MessageSegment.image(res["img"]), at_sender=True)

        if res.get("msg"):
            await group_message.send(res["msg"], at_sender=True)
