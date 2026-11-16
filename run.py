"""Two independent production entries. Never copy operator data from another install."""
from pathlib import Path
import argparse,os,runpy,shutil,sys

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description='启动千鸟酱或菲姆酱')
parser.add_argument('bot',choices=('testbot','testbot_2'))
parser.add_argument('--prepare',action='store_true',help='只生成缺失的本机配置，不覆盖现有配置或数据')
args=parser.parse_args()
if sys.version_info[:2]!=(3,12):raise SystemExit('请使用Python3.12虚拟环境。')
project=ROOT/args.bot
for folder in ('database','data/gacha','data/fight','data/learning_chat/local_intelligence'):
    (project/folder).mkdir(parents=True,exist_ok=True)
(ROOT/'runtime').mkdir(exist_ok=True)
for source,target in [(project/'.env.example',project/'.env'),(project/'defaults/love.json',project/'love.json')]:
    if source.is_file() and not target.exists():shutil.copyfile(source,target)
for source in (project/'defaults/fight').glob('*.json'):
    target=project/'data/fight'/source.name
    if not target.exists():shutil.copyfile(source,target)
card=project/'defaults/persona_card.txt';target=project/'data/learning_chat/local_intelligence/persona_card.txt'
if card.exists() and not target.exists():shutil.copyfile(card,target)
if args.prepare:
    print('已生成本机初始配置；请填写.env并补充docs/ASSETS.md中的资源。')
    raise SystemExit(0)
if not (project/'.env').exists():raise SystemExit('请先运行--prepare并填写.env。')
if args.bot=='testbot':
    assets=project/'testbot/plugins/testforsera/fortune_cards'
    if not any(assets.glob('*.png')):raise SystemExit('千鸟求签素材尚未补充，见docs/ASSETS.md；也可在bot.py停用对应插件。')
os.chdir(project)
sys.path[:0]=[str(ROOT/'shared'),str(project)]
runpy.run_path(str(project/'bot.py'),run_name='__main__')
