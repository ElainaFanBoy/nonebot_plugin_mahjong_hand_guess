import ujson
from nonebot import require
from sqlitedict import SqliteDict

require("nonebot_plugin_localstore")

from nonebot_plugin_localstore import get_data_dir

__dir = get_data_dir("nonebot_plugin_mahjong_hand_guess")


db = {}


def init_db(db_dir="db", db_name="db.sqlite", tablename="unnamed") -> SqliteDict:
    if db.get(db_name):
        return db[db_name]
    db[db_name] = SqliteDict(
        __dir.joinpath(db_dir, db_name).as_posix(),
        tablename=tablename,
        encode=ujson.dumps,
        decode=ujson.loads,
        autocommit=True,
    )
    return db[db_name]
