"""Optional bounded Chinese lexical lookup; never uploads group conversation."""
import asyncio,json,re,time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,unquote
import httpx
from testbot.plugins.chat_storage import read_json,write_json,locked

DEFAULTS={'开启':True,'缓存小时':168,'失败缓存分钟':10,'每分钟最多查询':2,
          '说明':'只查询模型判为需要核查的短词，优先简中内容；不上传群名、账号、完整聊天。无需另填搜索密钥。'}
_rates={}


class Results(HTMLParser):
    def __init__(self):
        super().__init__();self.entries=[];self.depth=0;self.h2=False;self.p=False;self.current=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='li':
            if self.current:self.depth+=1
            elif 'b_algo' in attrs.get('class','').split():self.current={'title':'','snippet':'','url':''};self.depth=1
        if self.current:
            if tag=='h2':self.h2=True
            elif tag=='p':self.p=True
            elif tag=='a' and self.h2 and not self.current['url']:self.current['url']=attrs.get('href','')
    def handle_endtag(self,tag):
        if not self.current:return
        if tag=='h2':self.h2=False
        elif tag=='p':self.p=False
        elif tag=='li':
            self.depth-=1
            if self.depth==0:self.entries.append(self.current);self.current=None;self.h2=False;self.p=False
    def handle_data(self,text):
        if self.current:
            if self.h2:self.current['title']+=text
            elif self.p:self.current['snippet']+=text


class BaiduResults(HTMLParser):
    def __init__(self):super().__init__();self.entries=[];self.current=None;self.depth=0;self.title=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='div':
            if self.current:self.depth+=1
            elif 'c-container' in attrs.get('class','').split():
                self.current={'title':'','snippet':'','url':''};self.depth=1
        if self.current:
            if tag=='h3':self.title=True
            elif tag=='a' and self.title and not self.current['url']:self.current['url']=attrs.get('href','')
    def handle_endtag(self,tag):
        if not self.current:return
        if tag=='h3':self.title=False
        elif tag=='div':
            self.depth-=1
            if self.depth==0:self.entries.append(self.current);self.current=None;self.title=False
    def handle_data(self,text):
        if self.current:
            self.current['title' if self.title else 'snippet']+=text+' '


def safe_term(term,question):
    if not isinstance(term,str):return ''
    term=term.strip()
    # It must be a literal short word in this message, not the whole question.
    if not re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9]{1,16}',term) or term not in question:return ''
    if re.search(r'\d{5,}|(?:sk|api|token|key|password)',term,re.I):return ''
    if len(term)>6 and term==question.strip():return ''
    return term


class LexicalSearch:
    def __init__(self,root,clock=time.time,transport=None):
        self.root=Path(root);self.clock=clock;self.transport=transport
        self.path=self.root/'网络词义.json';self.cache=self.root/'词义查询缓存.json'
    def config(self):
        with locked(self.path):
            if not self.path.exists():write_json(self.path,DEFAULTS)
            cfg=read_json(self.path,DEFAULTS,strict=True)
        if type(cfg.get('开启',True)) is not bool:raise ValueError('词义开关必须是布尔值')
        for k,low,high in [('缓存小时',1,720),('失败缓存分钟',1,60),('每分钟最多查询',0,10)]:
            if type(cfg.get(k,DEFAULTS[k])) is not int or not low<=cfg.get(k,DEFAULTS[k])<=high:raise ValueError('词义查询配置超出范围')
        return {**DEFAULTS,**cfg}
    def cached(self,term):
        with locked(self.cache):
            cache=read_json(self.cache,{})
        item=cache.get(term)
        if isinstance(item,dict) and item.get('until',0)>self.clock():return item.get('results',[])
        return None
    def remember(self,term,results,cfg):
        with locked(self.cache):
            cache=read_json(self.cache,{})
            cache={k:v for k,v in cache.items() if isinstance(v,dict) and v.get('until',0)>self.clock()}
            cache[term]={'until':self.clock()+(cfg['缓存小时']*3600 if results else cfg['失败缓存分钟']*60),'results':results}
            while len(cache)>256:cache.pop(next(iter(cache)))
            write_json(self.cache,cache)
    async def fetch(self,term):
        # Query only the word itself. zh-CN and CN market prefer simplified
        # Chinese results; documents are snippets, not executable instructions.
        query='"'+term+'" 网络用语 意思'
        async def page(client,url,params,parser):
            try:
                async with client.stream('GET',url,params=params,headers={'Accept-Language':'zh-CN,zh;q=0.9','User-Agent':'Mozilla/5.0'}) as response:
                    response.raise_for_status();raw=bytearray()
                    async for part in response.aiter_bytes():
                        raw.extend(part)
                        if len(raw)>900_000:raise ValueError('搜索响应过大')
                parser.feed(raw.decode('utf-8',errors='replace'))
                return parser.entries
            except (httpx.HTTPError,ValueError):return []
        async with httpx.AsyncClient(timeout=4,trust_env=False,follow_redirects=False,transport=self.transport) as client:
            pages=await asyncio.gather(
                page(client,'https://www.baidu.com/s',{'wd':query,'ie':'utf-8'},BaiduResults()),
                page(client,'https://cn.bing.com/search',{'q':query,'setlang':'zh-hans','cc':'CN','count':5},Results()))
        results=[]
        for entry in pages[0]+pages[1]:
            url=entry['url'];host=(urlsplit(url).hostname or '').lower()
            if not url.startswith('https://') or not host or host.endswith(('reddit.com','quora.com')):continue
            title=re.sub(r'\s+',' ',entry['title']).strip()[:80]
            snippet=re.sub(r'\s+',' ',entry['snippet']).strip()[:220]
            if not title or not snippet:continue
            combined=title+' '+snippet
            if term.casefold() not in combined.casefold():continue
            if not re.search(r'网络|用语|流行|梗|谐音|游戏|意思|含义|语境|缩写|简称',combined):continue
            # URLs are retained for honest provenance, never fetched or followed.
            results.append({'词':term,'标题':title,'摘要':snippet,'来源':url[:500]})
            if len(results)==2:break
        return results
    async def lookup(self,term,question):
        term=safe_term(term,question)
        if not term:return []
        try:
            cfg=await asyncio.to_thread(self.config)
            if not cfg['开启']:return []
            cached=await asyncio.to_thread(self.cached,term)
            if cached is not None:return cached
            key=str(self.root.resolve());now=self.clock()
            recent=[t for t in _rates.get(key,[]) if now-t<60]
            if len(recent)>=cfg['每分钟最多查询']:return []
            _rates[key]=recent+[now]
            try:results=await asyncio.wait_for(self.fetch(term),5)
            except (httpx.HTTPError,ValueError,asyncio.TimeoutError):results=[]
            await asyncio.to_thread(self.remember,term,results,cfg)
            return results
        except (OSError,ValueError,TypeError):return []
