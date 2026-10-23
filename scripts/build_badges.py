"""Bundle actual club crests and bind every club alias to a verified local file.

Input: cached JoseArroyave/football-logos ZIP plus historical supplemental crests.
No fuzzy matching, runtime hotlinking, or generated substitute badges.
"""
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import quote

try:
    from .import_rosters import normalized
except ImportError:
    from import_rosters import normalized

ROOT=Path(__file__).resolve().parents[1]
COUNTRIES={'en':'england','es':'spain','de':'germany','it':'italy','fr':'france'}
OVERRIDES={
 ('de','1kaiserslautern'):'FC_Kaiserslautern.svg',('de','1unionberlin'):'Union_Berlin.svg',('de','bayernmunich'):'Bayern_Munich.svg',('de','ingolstadt04'):'Ingolstadt.svg',('de','koln'):'Cologne.svg',
 ('en','brightonhovealbion'):'Brighton.svg',('en','ipswichtown'):'Ipswich.svg',('en','leicestercity'):'Leicester.svg',('en','tottenhamhotspur'):'Tottenham.svg',('en','westhamunited'):'West_Ham.svg',
 ('fr','amiens'):'Amiens_SC.svg',('fr','brest'):'Brest.svg',('fr','caen'):'Stade_Malherbe_Caen.svg',('fr','clermont'):'Clermont_Foot.svg',('fr','parissaintgermain'):'Paris_Saint-Germain_(PSG).svg',('fr','sochaux'):'FC_Sochaux-Montbéliard.svg',('fr','strasbourg'):'RC_Strasbourg_Alsace.svg',('it','monza'):'AC_Monza.svg',('it','roma'):'AS_Roma.svg',
}
SUPPLEMENTS={
 ('fr','arlesavignon'):('arles-crest.png','https://commons.wikimedia.org/wiki/File:AC_Arles-Avignon_logo.png'),
 ('fr','evianthonongaillard'):('evian-crest.svg','https://commons.wikimedia.org/wiki/File:Evian_Thonon_Gaillard_Football_Club_Croix_de_Savoie_logo_(2009%E2%80%932016).svg'),
}
PRESERVE={'Manchester City':'manchester-city','Arsenal':'arsenal','Liverpool':'liverpool','Chelsea':'chelsea','Barcelona':'barcelona','Real Madrid':'real-madrid'}


def validate_asset(body,suffix):
    if suffix=='.svg':
        root=ET.fromstring(body)
        if root.tag.split('}')[-1]!='svg':raise ValueError('Not an SVG')
        for el in root.iter():
            if el.tag.split('}')[-1] in ('script','foreignObject'):raise ValueError('Unsafe SVG element')
            for key,value in el.attrib.items():
                if key.lower().startswith('on'):raise ValueError('SVG event handler')
                if key.split('}')[-1] in ('href','src') and value and not value.startswith(('#','data:')):raise ValueError('External SVG resource')
        if not root.get('viewBox') and not (root.get('width') and root.get('height')):raise ValueError('SVG has no dimensions')
    elif suffix=='.png':
        if not body.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Not a PNG')
        width,height=struct.unpack('>II',body[16:24])
        if width<16 or height<16:raise ValueError('PNG too small')
    else:raise ValueError('Unsupported format')


def build():
    catalog_path=ROOT/'dist/catalog.json';catalog=json.loads(catalog_path.read_text())
    archive=zipfile.ZipFile(ROOT/'.local/sources/extra-club-logos.zip')
    assets=[p for p in archive.namelist() if p.endswith('.svg') and '/logos/' in p]
    directory=ROOT/'dist/assets/crests';directory.mkdir(exist_ok=True)
    records={};names={};identities={}
    for team in catalog['teams']:
        if team['kind']!='club':continue
        key=(team['competition'],normalized(team['name']))
        identity='-'.join(key)
        if identity not in records:
            if key in SUPPLEMENTS:
                filename,source=SUPPLEMENTS[key];suffix=Path(filename).suffix;body=(ROOT/'.local/sources'/filename).read_bytes()
            elif team['name'] in PRESERVE:
                filename=PRESERVE[team['name']]+'.svg';suffix='.svg';body=(directory/filename).read_bytes()
                source=next((r['source'] for r in records.values() if r['path'].endswith('/'+filename)),None) or {'Manchester City':'https://crests.football-data.org/65.svg','Arsenal':'https://crests.football-data.org/57.svg','Liverpool':'https://crests.football-data.org/64.svg','Chelsea':'https://crests.football-data.org/61.svg','Barcelona':'https://crests.football-data.org/81.svg','Real Madrid':'https://crests.football-data.org/86.svg'}[team['name']]
            else:
                country=COUNTRIES[team['competition']]
                options=[p for p in assets if '/logos/'+country+'/' in p]
                if key in OVERRIDES:matches=[p for p in options if p.rsplit('/',1)[-1]==OVERRIDES[key]]
                else:matches=[p for p in options if normalized(p.rsplit('/',1)[-1][:-4].replace('_',' '))==key[1]]
                if len(matches)!=1:raise ValueError(f'Unresolved badge: {team["name"]} ({key}), {matches}')
                original=matches[0];body=archive.read(original);suffix='.svg';source='https://github.com/JoseArroyave/football-logos/blob/main/'+quote(original.split('/',1)[1],safe='/')
            validate_asset(body,suffix)
            path='assets/crests/'+identity+suffix
            (ROOT/'dist'/path).write_bytes(body)
            records[identity]=dict(name=team['name'],competition=team['competition'],path=path,source=source,sha256=hashlib.sha256(body).hexdigest(),aliases=[])
        record=records[identity]
        if team['name'] not in record['aliases']:record['aliases'].append(team['name'])
        names[team['name']]=record['path'];team['crest']=record['path'];identities[team['id']]=identity
    manifest=dict(version=1,scope='Every club edition in catalog.json. Club identification crests, not a complete year-specific design history.',clubs=records,names=names,editions=identities)
    (directory/'clubs.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    catalog_path.write_text(json.dumps(catalog,ensure_ascii=False,separators=(',',':')))
    print(f'{len(records)} club identities; {len(names)} historical name variants; {len(identities)} club editions; 0 missing badges')

if __name__=='__main__':build()
