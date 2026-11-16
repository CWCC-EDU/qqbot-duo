from pathlib import Path
import ast,json,re,sys,warnings
ROOT=Path(__file__).resolve().parents[1]
failures=[];count=0
warnings.filterwarnings('ignore',category=SyntaxWarning)
for file in ROOT.rglob('*'):
    if not file.is_file() or '.git' in file.parts:continue
    relative=file.relative_to(ROOT).as_posix();count+=1
    if re.search(r'(?:^|/)(?:napcat[^/]*|qqnt|nt_qq|nt_data|nt_db)(?:/|$)|(?:^|/)(?:auth_token\.txt|webui\.json|onebot11_\d+\.json|cookies\.txt|qrcode[^/]*\.(?:png|jpg))$',relative,re.I):
        failures.append((relative,'协议端或QQ登录文件'))
    if file.name.startswith('.env') and file.name!='.env.example':failures.append((relative,'真实环境文件'))
    if file.suffix.lower() in ('.db','.sqlite','.sqlite3','.key','.log','.exe','.dll','.pyd'):failures.append((relative,'运行状态或密钥/二进制文件'))
    if any(part in ('database','cache','media-cache','data') for part in file.relative_to(ROOT).parts):failures.append((relative,'运行数据目录'))
    if file.suffix not in ('.py','.json','.txt','.md','.toml') and file.name!='.env.example':continue
    text=file.read_text(encoding='utf-8-sig',errors='strict')
    if file.suffix=='.py':
        try:ast.parse(text,filename=relative)
        except SyntaxError as exc:failures.append((relative,'语法错误:'+str(exc.lineno)))
    if file.suffix=='.json':
        try:json.loads(text)
        except ValueError:failures.append((relative,'JSON解析失败'))
    if file.name=='check_public.py':continue
    for number,line in enumerate(text.splitlines(),1):
        if re.search(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{15,}|github_pat_[A-Za-z0-9_]{15,})',line):
            failures.append((relative,f'疑似凭据:{number}'))
        if re.search(r'(?i)(?:secret_key|api_key|password|access_token)\s*[:=]\s*["\x27][^"\x27]{12,}["\x27]',line):
            failures.append((relative,f'硬编码敏感值:{number}'))
print(json.dumps({'files_checked':count,'passed':not failures,'failures':failures},ensure_ascii=False,indent=2))
raise SystemExit(bool(failures))
