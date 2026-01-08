import re
import random
import linecache
from enum import Enum
from pathlib import Path
from collections import defaultdict
from typing import Optional, TypedDict, NamedTuple

from PIL import Image
from nonebot.log import logger
from mahjong.tile import TilesConverter as TC
from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig

from .user import User
from .mahjong_image import MahjongImage, TilebackType
from .imghandler import get_font, easy_paste, draw_text_by_line

__dir = Path(__file__).parent


class TileAsciiMap(Enum):
    万 = "m"
    筒 = "p"
    索 = "s"
    东 = "1z"
    南 = "2z"
    西 = "3z"
    北 = "4z"
    白 = "5z"
    发 = "6z"
    中 = "7z"


TileMap = ["万", "筒", "索", "东", "南", "西", "北", "白", "发", "中"]


class HandSplit(NamedTuple):
    man: list
    pin: list
    sou: list
    honors: list


class HandResult(NamedTuple):
    tiles: list
    tiles_ascii: list
    win_tile: str
    tsumo: bool
    result: HandConfig
    raw: str
    hand_index: int


def get_hand(hand_index=None, **kwargs) -> HandResult:
    calculator = HandCalculator()

    hand_list = linecache.getlines(__dir.joinpath(
        "assets", "hands.txt").as_posix())  # 读取手牌列表
    hand_index = hand_index or random.randint(0, len(hand_list))  # 指定或者随机一组手牌
    hand_raw = hand_list[hand_index].strip()[:-3]
    raw = hand_raw.replace("+", "")
    tsumo = hand_raw[26] == "+"  # 是否为自摸
    last_tile = (hand_raw[26:28], hand_raw[27:29])[tsumo]  # 和牌

    tiles = TC.one_line_string_to_136_array(raw)
    win_tile = TC.one_line_string_to_136_array(last_tile)[0]

    result = calculator.estimate_hand_value(
        tiles,
        win_tile,
        config=HandConfig(is_riichi=True, is_tsumo=tsumo),
        **kwargs,
    )

    tiles = TC.one_line_string_to_136_array(hand_raw[:26])
    tiles_ascii = HandGuess.format_split_hand(hand_raw[:26])

    return HandResult(tiles, tiles_ascii, last_tile, tsumo, result, raw, hand_index)


class UserState(NamedTuple):
    hit_count: int


class GroupState(NamedTuple):
    start: bool
    hand: HandResult
    users: defaultdict


class GuessesResult(TypedDict):
    msg: str
    img: Optional[Image.Image]
    finish: bool


class HandGuess:
    __slots__ = ["user", "session", "info", "_status"]

    MAX_GUESS = 8  # 每人最大猜测次数
    GUESS_DEDUCT_POINTS = 200  # 超出每回扣除的积分
    SHOW_WIN_TILE_POINTS = 200  # 查看胡牌扣除积分

    TIMEOUT = 10 * 60  # 一局结束超时时间

    _record = set()

    def __init__(self, user: str, session: str):
        self.user = user
        self.session = session
        self.info = User(self.user)
        self._status: Optional[GroupState] = None

    @property
    def status(self) -> GroupState:
        if not self._status:
            raise RuntimeError("游戏未开始")
        return self._status

    def already_start(self):
        return self.session in self._record

    def reset_game(self):
        self._status = None
        self._record.discard(self.session)

    async def timeout(self):
        ans = await self.guesses_handler("", only_answer=True)
        self.reset_game()
        return ans

    def start(self):
        # 生成手牌
        hand_res = get_hand()
        self._record.add(self.session)
        self._status = GroupState(
            True, hand_res, defaultdict(lambda: UserState(0)))
        logger.debug(TC.to_one_line_string(hand_res.tiles) + hand_res.win_tile)

        return

    @staticmethod
    def format_hand_msg(msg: str):
        hand = ""
        for w in msg:
            if w in TileMap:
                hand += TileAsciiMap[w].value
            else:
                hand += w

        if hand[:-2][-1].isdigit():
            hand = hand[:-2] + hand[-1] + hand[-2:]
        return hand

    @staticmethod
    def format_split_hand(hand: str):
        split_start = 0
        result = ""
        for index, i in enumerate(hand):
            if i == "m":
                result += "m".join(hand[split_start:index]) + "m"
                split_start = index + 1
            if i == "p":
                result += "p".join(hand[split_start:index]) + "p"
                split_start = index + 1
            if i == "s":
                result += "s".join(hand[split_start:index]) + "s"
                split_start = index + 1
            if i == "z" or i == "h":
                result += "z".join(hand[split_start:index]) + "z"
                split_start = index + 1
        return [result[i * 2: i * 2 + 2] for i in range(int(len(result) / 2))]

    def inc_user_count(self):
        info = self.status.users[self.user]
        count = info.hit_count + 1
        self.status.users[self.user] = info._replace(hit_count=count)

    def is_win(self, tiles: list):
        set_tiles = self.status.hand.tiles_ascii + [self.status.hand.win_tile]
        return set_tiles == tiles

    def win_game(self, points: int):
        self.reset_game()
        self.info.add_points(points)
        return f" 恭喜你, 猜对了, 积分增加 {points} 点, 当前积分 {format(self.info.points, ',')}"

    def is_show_win_tile_msg(self, msg: str) -> Optional[GuessesResult]:
        if msg != "查看和牌":
            return
        if self.info.points < self.SHOW_WIN_TILE_POINTS:
            return {"msg": f" 你的积分({self.info.points})不足", "img": None, "finish": False}

        self.info.sub_points(self.SHOW_WIN_TILE_POINTS)
        blue = MahjongImage(TilebackType.blue)
        return {"msg": "", "img": blue.tile(self.status.hand.win_tile), "finish": False}

    async def guesses_handler(self, msg: str, only_answer=False) -> Optional[GuessesResult]:
        msg = (msg, self.status.hand.raw)[only_answer]
        msg = msg.strip().replace(" ", "")

        if show_win_tile := self.is_show_win_tile_msg(msg):
            return show_win_tile

        # pass不合法的信息
        if re.search(rf"[^\dmpszh{''.join(TileMap)}]", msg):
            return
        if len(msg) < 10:
            return

        use_deduct_points = False
        if self.status.users[self.user].hit_count >= self.MAX_GUESS and not only_answer:
            if self.info.points < self.GUESS_DEDUCT_POINTS:
                return {"msg": f" 你的积分({self.info.points})不足", "img": None, "finish": True}
            else:
                use_deduct_points = True
                self.info.sub_points(self.GUESS_DEDUCT_POINTS)

        msg_hand = HandGuess.format_hand_msg(msg)
        msg_win_tile = msg_hand[-2:]

        msg_tiles = TC.one_line_string_to_136_array(msg_hand)
        if len(msg_tiles) != 14:
            return {"msg": " 不是, 说好的14张牌呢", "img": None, "finish": False}

        win_tile = TC.one_line_string_to_136_array(msg_win_tile)[0]
        calculator = HandCalculator()
        # 默认立直 , 是否自摸看生成的牌组
        result = calculator.estimate_hand_value(
            msg_tiles,
            win_tile,
            config=HandConfig(is_riichi=True, is_tsumo=self.status.hand.tsumo),
        )

        if result.han is None:
            return {"msg": " 你这牌都没胡啊", "img": None, "finish": False}
        if result.han == 0:
            return {"msg": " 你无役了", "img": None, "finish": False}

        current_tiles = HandGuess.format_split_hand(msg_hand[:-2])

        blue = MahjongImage(TilebackType.blue)
        orange = MahjongImage(TilebackType.orange)
        no_color = MahjongImage(TilebackType.no_color)

        # === 14张一起做 Wordle 判色（修复重复牌 + 第14张单独判定导致的误判） ===
        answer_tiles_14 = self.status.hand.tiles_ascii + [self.status.hand.win_tile]
        guess_tiles_14 = current_tiles + [msg_win_tile]

        remain = defaultdict(int)
        for t in answer_tiles_14:
            remain[t] += 1

        colors = [None] * 14  # "blue" | "orange" | "gray"

        # 第一轮：位置完全正确 -> 蓝
        for i in range(14):
            if guess_tiles_14[i] == answer_tiles_14[i] and remain[guess_tiles_14[i]] > 0:
                colors[i] = "blue"
                remain[guess_tiles_14[i]] -= 1

        # 第二轮：存在但位置不对 -> 黄，否则灰
        for i in range(14):
            if colors[i] is not None:
                continue
            t = guess_tiles_14[i]
            if remain.get(t, 0) > 0:
                colors[i] = "orange"
                remain[t] -= 1
            else:
                colors[i] = "gray"
        # === 判色结束 ===

        # 手牌
        hand_img = Image.new("RGB", (80 * 13, 130), "#6c6c6c")
        for index, tile in enumerate(current_tiles):
            pos = (index * 80, 0)
            c = colors[index]
            if c == "blue":
                easy_paste(hand_img, blue.tile(tile), pos)
            elif c == "orange":
                easy_paste(hand_img, orange.tile(tile), pos)
            else:
                easy_paste(hand_img, no_color.tile(tile), pos)

        # 胡牌（第14张）
        wind_img = Image.new("RGB", (80, 130), "#6c6c6c")
        pos = (0, 0)
        c = colors[13]
        if c == "blue":
            easy_paste(wind_img, blue.tile(msg_win_tile), pos)
        elif c == "orange":
            easy_paste(wind_img, orange.tile(msg_win_tile), pos)
        else:
            easy_paste(wind_img, no_color.tile(msg_win_tile), pos)

        # 役提示
        yaku = [x for x in self.status.hand.result.yaku if x.yaku_id not in [0, 1]]
        yaku.reverse()
        tip = "提示: " + " ".join([x.japanese for x in yaku])

        # 番提示
        status_han = self.status.hand.result.han
        status_fu = self.status.hand.result.fu
        status_cost = self.status.hand.result.cost["main"] + \
            self.status.hand.result.cost["additional"]
        tsumo_tip = ("", ",自摸")[self.status.hand.tsumo]
        han_tip = f"{status_han}番{status_fu}符 {status_cost}点 (包括立直{tsumo_tip})"

        background = Image.new("RGB", (1200, 400), "#EEEEEE")

        if not only_answer:
            if use_deduct_points:
                draw_text_by_line(
                    background,
                    (26.5, 25),
                    f"-200 ({format(self.info.points, ',')})",
                    get_font(30),
                    "#475463",
                    255,
                )
            else:
                last = self.MAX_GUESS - \
                    self.status.users[self.user].hit_count - 1
                draw_text_by_line(background, (26.5, 25),
                                  f"剩余{last}回", get_font(40), "#475463", 255)

            draw_text_by_line(
                background,
                (26.5, 70),
                f"超出每回扣除{self.GUESS_DEDUCT_POINTS}积分",
                get_font(30, "65"),
                "#475463",
                800,
            )

        draw_text_by_line(background, (403.5, 25), tip,
                          get_font(40), "#475463", 800, True)
        draw_text_by_line(
            background,
            (194.5, 130),
            han_tip,
            get_font(40),
            "#475463",
            1200,
            True,
        )

        draw_text_by_line(
            background,
            (900, 25),
            f"支付{self.SHOW_WIN_TILE_POINTS}点[查看和牌]",
            get_font(25),
            "#475463",
            500,
        )

        easy_paste(background, hand_img.convert("RGBA"), (30, 226))
        easy_paste(background, wind_img.convert("RGBA"), (13 * 80 + 50, 226))

        if not only_answer:
            if self.is_win(current_tiles + [msg_win_tile]):
                return {"msg": self.win_game(status_cost), "img": background, "finish": True}
            self.inc_user_count()

        return {"msg": "", "img": background, "finish": False}
