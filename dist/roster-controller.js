import {suggestedXI,lineupError} from './squads.js';
const $=id=>document.getElementById(id);
const element=(tag,className,text)=>{const el=document.createElement(tag);if(className)el.className=className;if(text!==undefined)el.textContent=text;return el;};
export function createSquadController(manifest,onChange){
 const cache=new Map(),pending=new Map(),selection=new Map(),shown={};
 const initial=new URLSearchParams(location.search);
 async function load(edition){
  if(!manifest.editions[edition.id])return null;
  if(cache.has(edition.id))return cache.get(edition.id);
  if(!pending.has(edition.id))pending.set(edition.id,(async()=>{const response=await fetch(manifest.editions[edition.id].path);if(!response.ok)throw new Error('Squad could not be loaded. Reload to retry.');const data=await response.json();cache.set(edition.id,data);return data;})().finally(()=>pending.delete(edition.id)));
  return pending.get(edition.id);
 }
 const key=(side,edition)=>side+':'+edition.id;
 function players(edition,side){const data=cache.get(edition.id);return data?data.players.filter(p=>(selection.get(key(side,edition))||[]).includes(p.id)):[];}
 function error(edition,side){if(!manifest.editions[edition.id])return null;if(!cache.has(edition.id))return 'Loading squad…';return lineupError(players(edition,side));}
 function render(side,edition,data){
  const root=$(side+'-squad');root.replaceChildren();
  if(!data){$(side+'-squad-summary').textContent='Squad not available';root.append(element('p','squad-note','No sourced roster for this edition. Events use anonymous team units.'));return;}
  if(!selection.has(key(side,edition))){
   const explicit=initial.get(side)===edition.id?initial.get(side+'_xi'):null;
   selection.set(key(side,edition),explicit!==null?explicit.split(',').filter(Boolean):suggestedXI(data.players).map(p=>p.id));
  }
  $(side+'-squad-summary').textContent=`Squad & coach / ${data.players.length} players`;
  const coach=element('p','squad-coach');coach.append(element('strong','', 'COACH RECORDED IN SOURCE'),document.createTextNode(data.coaches.map(c=>c.name).join(' / ')||'Not recorded in source'));root.append(coach);
  root.append(element('p','squad-note','Suggested XI uses positions, not historical starting frequency. Select 11 players including one goalkeeper. Player names affect event attribution; player and coach ratings are not modeled.'));
  const controls=element('div','squad-lineup-controls'),count=element('span','squad-lineup-count');count.setAttribute('aria-live','polite');
  const auto=element('button','', 'Reset suggested XI');auto.type='button';auto.onclick=()=>{selection.set(key(side,edition),suggestedXI(data.players).map(p=>p.id));render(side,edition,data);onChange();};controls.append(count,auto);root.append(controls);
  const search=element('label','squad-search','Search squad');const input=document.createElement('input');input.type='search';input.placeholder='Player name or position';search.append(input);root.append(search);
  const list=element('div','squad-list'),checks=[];root.append(list);
  function paint(){const ids=selection.get(key(side,edition)),err=lineupError(players(edition,side));count.textContent=`${ids.length}/11 selected${err?' · '+err:''}`;count.classList.toggle('squad-status-error',Boolean(err));for(const {box,player} of checks){box.checked=ids.includes(player.id);box.disabled=player.status==='departed'||(!box.checked&&ids.length>=11);}}
  for(const player of data.players){const label=element('label','squad-player'+(player.status==='departed'?' departed':''));const box=document.createElement('input');box.type='checkbox';box.setAttribute('aria-label','Select '+player.name);label.append(box,element('span','player-number',player.number||'—'),element('span','',player.name+(player.status==='departed'?' · departed':'')),element('span','player-position',player.position));list.append(label);checks.push({box,player});box.onchange=()=>{const ids=selection.get(key(side,edition));selection.set(key(side,edition),box.checked?[...ids,player.id]:ids.filter(id=>id!==player.id));paint();onChange();};}
  input.oninput=()=>{const q=input.value.toLocaleLowerCase().trim();for(const {box,player} of checks)box.parentElement.hidden=!`${player.name} ${player.position}`.toLocaleLowerCase().includes(q);};
  const source=element('a','squad-source','View historical squad source ↗');source.href=data.source;source.target='_blank';source.rel='noreferrer';root.append(source);paint();
 }
 async function show(side,edition){shown[side]=edition?.id;if(!edition){$(side+'-squad').replaceChildren();return;}
  $(side+'-squad-summary').textContent='Loading squad & coach…';
  try{const data=await load(edition);if(shown[side]!==edition.id)return;render(side,edition,data);onChange();}catch(e){if(shown[side]!==edition.id)return;$(side+'-squad-summary').textContent='Squad load failed';$(side+'-squad').replaceChildren(element('p','squad-note',e.message));onChange();}
 }
 async function configuration(side,edition){const data=await load(edition);if(data&&!selection.has(key(side,edition)))render(side,edition,data);const err=error(edition,side);if(err)throw new Error(edition.name+': '+err);return players(edition,side);}
 return {show,error,configuration,coaches:edition=>cache.get(edition.id)?.coaches||[]};
}
