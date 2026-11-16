"""Back up and upgrade only this bot's ORM database before starting its server."""
from argparse import Namespace
from datetime import datetime
from pathlib import Path
import asyncio,importlib,json,os,sqlite3
ROOT=Path(__file__).resolve().parent
os.chdir(ROOT)
import bot
import nonebot_plugin_orm as orm
from sqlalchemy.util import greenlet_spawn

async def run():
    orm._init_orm()
    backups=[]
    try:
        for engine in orm._engines.values():
            if not engine.url.drivername.startswith('sqlite'):
                raise RuntimeError('此自动升级器只处理本机SQLite，请先人工迁移外部数据库。')
            database=engine.url.database
            if not database or database==':memory:':continue
            path=Path(database).resolve()
            if not path.is_relative_to(ROOT):raise RuntimeError('数据库不在当前机器人目录，已停止升级。')
            if path.exists():
                backup=ROOT/'data/maintenance-backups'/('orm-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))/path.relative_to(ROOT)
                backup.parent.mkdir(parents=True,exist_ok=True)
                with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as source:
                    with sqlite3.connect(backup) as target:source.backup(target)
                backups.append(str(backup.relative_to(ROOT)))
        command=Namespace(cmd=(orm.migrate.upgrade,[],[]))
        with orm.migrate.AlembicConfig(cmd_opts=command) as config:
            await greenlet_spawn(orm.migrate.upgrade,config)
            command.cmd=(orm.migrate.check,[],[])
            await greenlet_spawn(orm.migrate.check,config)
        print('数据库升级检查通过。原数据库备份：'+('、'.join(backups) or '无旧数据库'),flush=True)
    finally:
        for engine in orm._engines.values():await engine.dispose()

if __name__=='__main__':asyncio.run(run())
