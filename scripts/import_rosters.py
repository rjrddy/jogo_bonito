"""Import historical FootballSquads snapshots for this non-commercial project.

Attribution required: https://www.footballsquads.co.uk/tou.htm
Caches pages, limits concurrency, records exact sources/hashes, and reports gaps.
"""
import argparse
import hashlib
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.local/rosters'
BASE = 'https://www.footballsquads.co.uk/'
NOTICE = 'Source of Material is http://www.footballsquads.com. Material: © FootballSquads.com, 1999 - , All Rights Reserved'


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[];self.rows=[];self.row=None;self.cell=None;self.href=None;self.anchor=[];self.text=[];self.headings=[];self.heading=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='a':self.href=attrs.get('href');self.anchor=[]
        if tag=='tr':self.row=[]
        if tag in ('td','th') and self.row is not None:self.cell=[]
        if tag in ('h2','h3'):self.heading=[]
    def handle_data(self,data):
        self.text.append(data)
        if self.href is not None:self.anchor.append(data)
        if self.cell is not None:self.cell.append(data)
        if self.heading is not None:self.heading.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.href is not None:
            self.links.append((self.href,' '.join(' '.join(self.anchor).split())));self.href=None
        if tag in ('td','th') and self.cell is not None:
            if self.row is not None:self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell=None
        if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None
        if tag in ('h2','h3') and self.heading is not None:self.headings.append(' '.join(' '.join(self.heading).split()));self.heading=None


def get(url,offline=False):
    path=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.html')
    if path.exists():body=path.read_bytes()
    else:
        if offline:raise FileNotFoundError(url)
        for attempt in range(3):
            try:
                with urlopen(Request(url,headers={'User-Agent':'JogoBonito/0.3 personal-noncommercial-research'}),timeout=35) as response:body=response.read()
                path.write_bytes(body);break
            except Exception:
                if attempt==2:raise
                time.sleep(1+attempt)
        time.sleep(.18)
    try:html=body.decode('utf-8')
    except UnicodeDecodeError:html=body.decode('cp1252',errors='replace')
    page=Page();page.feed(html)
    return page,hashlib.sha256(body).hexdigest()


def roster(page,url,digest):
    players=[];departed=False
    for cells in page.rows:
        whole=' '.join(cells).lower()
        if any(marker in whole for marker in ('players no longer','players who left','players who have left','players leaving')):departed=True
        if len(cells)<4:continue
        number,name,nationality,position=cells[:4]
        if not name or not re.fullmatch(r'[GDMFA/ -]{1,7}',position) or name.lower()=='name':continue
        players.append(dict(id=hashlib.sha256((name+'|'+(cells[6] if len(cells)>6 else '')).encode()).hexdigest()[:16],name=name,number=number or None,position=position,nationality=nationality,date_of_birth=cells[6] if len(cells)>6 else None,status='departed' if departed else 'listed'))
    # Header is the source's snapshot manager, not a claim about every spell.
    coaches=[]
    for heading in page.headings:
        match=re.search(r'(?:Manager|Coach|Head Coach):\s*(.+)',heading,re.I)
        if match and match[1].strip():coaches.append(dict(name=match[1].strip(),role='Source snapshot coach'))
    unique={p['id']:p for p in players}
    return dict(players=list(unique.values()),coaches=coaches,source=url,source_sha256=digest,scope='Source squad snapshot; includes separately marked departed players when listed.',status='available' if len(unique)>=11 else 'partial')


ALIASES={
 'internazionale':'inter','internazionalemilano':'inter','intermilan':'inter','parissg':'parissaintgermain','parisstgermain':'parissaintgermain','olympiquedemarseille':'marseille','olympiquelyonnais':'lyon','asmonaco':'monaco','girondinsbordeaux':'bordeaux','girondinsdebordeaux':'bordeaux','saintetienne':'stetienne','fcsanktpauli':'stpauli','sanktpauli':'stpauli','1fckoln':'koln','1fcunionberlin':'unionberlin','tsg1899hoffenheim':'hoffenheim','1899hoffenheim':'hoffenheim','tsghoffenheim':'hoffenheim','athleticclubbilbao':'athleticbilbao','athleticclub':'athleticbilbao','deportivolacoruna':'deportivolacoruna','deportivolacoruna':'deportivolacoruna','sportinggijon':'sportinggijon','sportingdegijon':'sportinggijon','queensparkrangers':'qpr','wolverhamptonwanderers':'wolves','westbromwichalbion':'westbrom','bayer04leverkusen':'bayerleverkusen','1fckaiserslautern':'kaiserslautern','1fcnurnberg':'nurnberg','1fcnurnberg':'nurnberg','fsvmainz05':'mainz','1fsvmainz05':'mainz','mainz05':'mainz','svdarmstadt98':'darmstadt','darmstadt98':'darmstadt','fortunausseldorf':'fortunadusseldorf','fortuna95dusseldorf':'fortunadusseldorf','fortunadusseldorf':'fortunadusseldorf','1fcbochum':'bochum','vflbochum':'bochum','southkorea':'korearepublic','northkorea':'koreadpr','unitedstates':'usa','unitedstatesofamerica':'usa','ivorycoast':'cotedivoire','republicofireland':'ireland','czechia':'czechrepublic','turkiye':'turkey','bayernmunchen':'bayernmunich','bayernmuenchen':'bayernmunich',
}

ALIASES.update({'1koeln': 'koln', '1koln': 'koln', '1nuernberg': 'nurnberg', '1nurnberg': 'nurnberg', '1heidenheim1846': 'heidenheim', '1heidenheim': 'heidenheim', 'pisa1909': 'pisa', 'acffiorentina': 'fiorentina', 'ajauxerre': 'auxerre', 'nancylorraine': 'nancy', 'angerssco': 'angers', 'atalantabc': 'atalanta', 'bologna1909': 'bologna', 'bormoenchengladbach': 'borussiamonchengladbach', 'bormonchengladbach': 'borussiamonchengladbach', 'clermontfoot63': 'clermont', 'como1907': 'como', 'delfinopescara': 'pescara', 'deportivoalaves': 'alaves', 'dijonfco': 'dijon', 'eaguingamp': 'guingamp', 'estactroyes': 'troyes', 'espanyolbarcelona': 'espanyol', 'stpauli1910': 'stpauli', 'genoacfc': 'genoa', 'grenoblefoot38': 'grenoble', 'hellasverona': 'verona', 'hertha': 'herthaberlin', 'lazioroma': 'lazio', 'lilleosc': 'lille', 'montpellierhsc': 'montpellier', 'netherlands': 'holland', 'nimesolympique': 'nimes', 'ogcnice': 'nice', 'olympiquelyon': 'lyon', 'olympiquemarseille': 'marseille', 'parma1913': 'parma', 'celta': 'celtavigo', 'celtadevigo': 'celtavigo', 'strasbourgalsace': 'strasbourg', 'espanyoldebarcelona': 'espanyol', 'racingclubdelens': 'lens', 'rayovallecanodemadrid': 'rayovallecano', 'realbetis': 'betis', 'realbetisbalompie': 'betis', 'realoviedo': 'oviedo', 'realsociedaddefutbol': 'realsociedad', 'realvalladolid': 'valladolid', 'realzaragoza': 'zaragoza', 'paderborn07': 'paderborn', 'sdeibar': 'eibar', 'sdhuesca': 'huesca', 'smcaen': 'caen', 'spal2013ferrara': 'spal', 'spvgggreutherfurth1903': 'spvgggreutherfurth', 'stadebrest': 'brest', 'stadebrestois29': 'brest', 'stadereims': 'reims', 'staderennais': 'rennes', 'staderennais1901': 'rennes', 'staderennes': 'rennes', 'stadedereims': 'reims', 'ucsampdoria': 'sampdoria', 'salernitana1919': 'salernitana', 'bochum1848': 'bochum'})

def normalized(name):
    text=''.join(c for c in unicodedata.normalize('NFKD',name.lower()) if not unicodedata.combining(c))
    text=re.sub(r'\b(fc|cf|afc|ac|sc|as|rc|rcd|ud|cd|ca|us|ss|ssc|sv|vfb|vfl|bsc|calcio|football club|club de futbol)\b','',text)
    text=re.sub(r'[^a-z0-9]','',text)
    for _ in range(3):
        text=ALIASES.get(text,text)
    return text


def main(offline=False):
    CACHE.mkdir(parents=True,exist_ok=True)
    catalog=json.loads((ROOT/'dist/catalog.json').read_text())
    archive,_=get(BASE+'archive.htm',offline);national,_=get(BASE+'national.htm',offline)
    indexes={}
    for href,_ in archive.links:
        m=re.fullmatch(r'(eng|spain|ger|italy|france)/(\d{4})-(\d{4})/(faprem|engprem|laliga|spalali|gerbun|seriea|fralig1)\.htm',href)
        if m and 2010<=int(m[3])<=2026:indexes[({'eng':'en','spain':'es','ger':'de','italy':'it','france':'fr'}[m[1]],int(m[3]))]=urljoin(BASE,href)
    for href,_ in national.links:
        m=re.fullmatch(r'national/(worldcup|eurocham|copaamer)/(?:wc|euro|copa)(\d{4})\.htm',href)
        if m and int(m[2])>=2010:
            code={'worldcup':'wc','eurocham':'euros','copaamer':'copa'}[m[1]];year=int(m[2]);year=2021 if code=='euros' and year==2020 else year
            indexes[(code,year)]=urljoin(BASE,href)
    tasks=[];errors=[];unmatched=[]
    def index_task(item):
        (code,year),url=item;page,_=get(url,offline)
        candidates=catalog['teams'];candidates=[t for t in candidates if t['competition']==code and t['year']==year]
        links=[]
        for href,name in page.links:
            target=urljoin(url,href)
            if name and target.startswith(url[:-4]+'/') and target.endswith('.htm'):links.append((name,target))
        # Some index filenames differ from their squad subdirectory. Use same
        # parent directory, exactly one subdirectory level, and team-like anchors.
        if not links:
            parent=url.rsplit('/',1)[0]+'/'
            links=[(name,urljoin(url,href)) for href,name in page.links if name and urljoin(url,href).startswith(parent) and urljoin(url,href).count('/')==parent.count('/')+1 and href.endswith('.htm')]
        found=[]
        for t in candidates:
            exact=[(name,target) for name,target in links if normalized(name)==normalized(t['name'])]
            if len(exact)==1:found.append((t['id'],exact[0][1]))
            else:unmatched.append(dict(id=t['id'],name=t['name'],normalized=normalized(t['name']),index=url,candidates=[n for n,_ in links]))
        return found
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(index_task,item):item for item in indexes.items()}
        for f in as_completed(futures):
            try:tasks.extend(f.result())
            except Exception as e:errors.append(dict(index=futures[f][1],error=str(e)))
    print(f'{len(indexes)} indexes, {len(tasks)} matched editions, {len(unmatched)} name mappings to resolve',flush=True)
    output={}
    def load(item):
        tid,url=item;page,digest=get(url,offline);return tid,roster(page,url,digest)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(load,item):item for item in tasks}
        for i,f in enumerate(as_completed(futures),1):
            try:
                tid,data=f.result();output[tid]=data
            except Exception as e:errors.append(dict(team_id=futures[f][0],error=str(e)))
            if i%100==0:print(f'Imported {i}/{len(tasks)} roster pages',flush=True)
    report=dict(attribution=NOTICE,terms=BASE+'tou.htm',usage='Non-commercial only with attribution',rosters=output,missing=[t['id'] for t in catalog['teams'] if t['id'] not in output],mapping_gaps=unmatched,errors=errors)
    (CACHE/'normalized.json').write_text(json.dumps(report,ensure_ascii=False,separators=(',',':')))
    (CACHE/'import-report.json').write_text(json.dumps(dict(missing=report['missing'],mapping_gaps=unmatched,errors=errors),ensure_ascii=False,indent=2))
    print(f'{len(output)} rosters / {len(catalog["teams"])} editions; {sum(len(r["players"]) for r in output.values())} player records; {sum(bool(r["coaches"]) for r in output.values())} coaches; {len(errors)} errors',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--offline',action='store_true');main(p.parse_args().offline)
