// Badge-derived palettes, with familiar primary colours reviewed for major clubs.
const reviewed={
 'en-manchestercity':['#6cabdd','#1c2c5b','#d4a12a'], 'en-arsenal':['#ef0107','#d8aa43','#063672'],
 'en-liverpool':['#c8102e','#00b2a9'], 'en-manchesterunited':['#da291c','#fbe122'],
 'en-chelsea':['#034694','#d1a843'], 'en-tottenhamhotspur':['#132257','#ffffff'],
 'es-barcelona':['#a50044','#004d98','#edbb00'], 'es-realmadrid':['#ffffff','#443c8e','#d6ae36'],
 'it-juventus':['#171717','#ffffff'], 'it-inter':['#0068a8','#111111'],
 'it-milan':['#fb090b','#111111'], 'it-napoli':['#12a0d7','#ffffff'],
 'it-roma':['#8e1f2f','#f0bc42'], 'it-lazio':['#87d8f7','#ffffff'],
 'de-bayernmunich':['#dc052d','#0066b2'], 'de-borussiadortmund':['#fde100','#111111'],
 'fr-parissaintgermain':['#004170','#da291c'], 'fr-marseille':['#00a5dc','#d7ad53']
};
const nations={Argentina:['#75aadb','#ffffff'],Brazil:['#ffdf00','#009739'],France:['#002395','#ed2939'],Spain:['#aa151b','#f1bf00'],Germany:['#171717','#ffce00'],Italy:['#0066b2','#009246'],England:['#ffffff','#ce1124'],Portugal:['#ce1126','#006b3f'],Netherlands:['#ff8200','#21468b'],Uruguay:['#5eb6e4','#f4d03f'],Belgium:['#ed2939','#fdda24'],Croatia:['#ed1c24','#171796'],Mexico:['#006847','#ce1126'],Colombia:['#fcd116','#003893'],Chile:['#d52b1e','#0039a6']};
const rgb=hex=>hex.match(/[a-f\d]{2}/gi).map(v=>parseInt(v,16));
const hex=channels=>'#'+channels.map(v=>Math.round(v).toString(16).padStart(2,'0')).join('');
const mix=(a,b,t)=>hex(rgb(a).map((v,i)=>v*(1-t)+rgb(b)[i]*t));
const luminance=c=>rgb(c).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
export function contrast(a,b){const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
export function readable(color,dark=false){const surfaces=dark?['#142019','#1a2a1f']:['#f2f1e9','#f9f8f1'];const target=dark?'#ffffff':'#000000';for(let i=0;i<=100;i++){const c=mix(color,target,i/100);if(surfaces.every(bg=>contrast(c,bg)>=4.5))return c;}return target;}
export function paletteFor(edition,data){const key=edition.crest?.split('/').pop().replace(/\.(svg|png)$/,'');const sampled=data.palettes?.[edition.crest]?.colors;return reviewed[key]||(sampled?.length?sampled:null)||nations[edition.name]||['#171717','#ffffff'];}
export function matchColors(home,away,data){const h=paletteFor(home,data),a=paletteFor(away,data);let other=a[0];if(contrast(h[0],other)<1.7){other=a.slice(1).find(c=>contrast(h[0],c)>=1.7)||other;}return {home:h[0],away:other};}
export function applyTeamColors(match,data,dark=false,root=document.documentElement){const colors=matchColors(match.home_edition,match.away_edition,data);for(const side of ['home','away']){const color=colors[side];root.style.setProperty('--'+side,color);root.style.setProperty('--'+side+'-rgb',rgb(color).join(', '));root.style.setProperty('--'+side+'-text',readable(color,dark));root.style.setProperty('--'+side+'-chart',readable(color,dark));root.style.setProperty('--'+side+'-on',contrast(color,'#ffffff')>=contrast(color,'#111111')?'#ffffff':'#111111');}return colors;}
