"""Bundle flag-icons v7.2.3 SVGs and attach them to every national edition.

Usage: python3 scripts/build_flags.py /path/to/flag-icons-v7.2.3.zip
Source: https://github.com/lipis/flag-icons (MIT). No runtime hotlinks.
"""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CODES=dict(line.split('=') for line in '''Albania=al
Algeria=dz
Argentina=ar
Australia=au
Austria=at
Belgium=be
Bolivia=bo
Bosnia and Herzegovina=ba
Brazil=br
Cameroon=cm
Canada=ca
Cape Verde=cv
Chile=cl
Colombia=co
Costa Rica=cr
Croatia=hr
Curaçao=cw
Czech Republic=cz
DR Congo=cd
Denmark=dk
Ecuador=ec
Egypt=eg
England=gb-eng
Finland=fi
France=fr
Georgia=ge
Germany=de
Ghana=gh
Greece=gr
Haiti=ht
Honduras=hn
Hungary=hu
Iceland=is
Iran=ir
Iraq=iq
Italy=it
Ivory Coast=ci
Jamaica=jm
Japan=jp
Jordan=jo
Mexico=mx
Morocco=ma
Netherlands=nl
New Zealand=nz
Nigeria=ng
North Korea=kp
North Macedonia=mk
Northern Ireland=gb-nir
Norway=no
Panama=pa
Paraguay=py
Peru=pe
Poland=pl
Portugal=pt
Qatar=qa
Republic of Ireland=ie
Romania=ro
Russia=ru
Saudi Arabia=sa
Scotland=gb-sct
Senegal=sn
Serbia=rs
Slovakia=sk
Slovenia=si
South Africa=za
South Korea=kr
Spain=es
Sweden=se
Switzerland=ch
Tunisia=tn
Turkey=tr
Ukraine=ua
United States=us
Uruguay=uy
Uzbekistan=uz
Venezuela=ve
Wales=gb-wls'''.splitlines())


def flag_path(name):
    return f'assets/flags/{CODES[name]}.svg'


def build(archive):
    catalog_path=ROOT/'dist/catalog.json'
    catalog=json.loads(catalog_path.read_text())
    names={t['name'] for t in catalog['teams'] if t['kind']=='national'}
    if names-set(CODES):raise ValueError(f'Missing flag mappings: {names-set(CODES)}')
    destination=ROOT/'dist/assets/flags';destination.mkdir(parents=True,exist_ok=True)
    records={}
    with zipfile.ZipFile(archive) as z:
        prefix='flag-icons-7.2.3/'
        for name in sorted(names):
            code=CODES[name];body=z.read(f'{prefix}flags/4x3/{code}.svg')
            (destination/f'{code}.svg').write_bytes(body)
            records[name]={'code':code,'path':flag_path(name),'sha256':hashlib.sha256(body).hexdigest()}
        (destination/'LICENSE').write_bytes(z.read(prefix+'LICENSE'))
    (destination/'index.json').write_text(json.dumps({'version':1,'source':'https://github.com/lipis/flag-icons/tree/v7.2.3','license':'MIT','teams':records},indent=2)+'\n')
    for t in catalog['teams']:
        if t['kind']=='national':t['crest']=flag_path(t['name'])
    catalog_path.write_text(json.dumps(catalog,separators=(',',':'))+'\n')
    print(f'Bundled {len(records)} national flags.')

if __name__=='__main__':build(sys.argv[1])
