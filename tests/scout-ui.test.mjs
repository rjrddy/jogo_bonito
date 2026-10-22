// Wiring test for the Scout lab controller.
//
// There is no browser and no dependency budget for one, so this drives the real
// dist/scout.js against a minimal DOM backed by the real dist/index.html: every
// element it reaches for must exist in the markup with a usable default, and
// every render path must run. It checks wiring and control flow, not layout.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const html=fs.readFileSync('dist/index.html','utf8');

// ---- Parse the ids the markup actually declares, with select/input defaults.
const declared=new Map();
for(const match of html.matchAll(/<(\w+)([^>]*\sid="([^"]+)"[^>]*)>/g)){
 const [,tag,attributes,id]=match;
 const entry={tag:tag.toLowerCase(),value:''};
 const value=/\svalue="([^"]*)"/.exec(attributes);
 if(value)entry.value=value[1];
 if(entry.tag==='select'){
  const body=html.slice(match.index,html.indexOf('</select>',match.index));
  const options=[...body.matchAll(/<option([^>]*)>/g)].map(o=>o[1]);
  const chosen=options.find(o=>/\sselected/.test(o))||options[0]||'';
  const optionValue=/\svalue="([^"]*)"/.exec(chosen);
  entry.value=optionValue?optionValue[1]:'';
  entry.options=options.length;
 }
 declared.set(id,entry);
}
assert.ok(declared.has('scout-view'),'index.html must declare the scout view');

const missing=[];
class Element{
 constructor(tag='div'){
  this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.dataset={};
  this.style={setProperty(){},};this._text='';this.value='';this.hidden=false;this.className='';
  this.classList={
   list:new Set(),
   add:(...names)=>names.forEach(n=>this.classList.list.add(n)),
   remove:(...names)=>names.forEach(n=>this.classList.list.delete(n)),
   toggle:(name,force)=>{const on=force===undefined?!this.classList.list.has(name):force;
    on?this.classList.list.add(name):this.classList.list.delete(name);return on;},
   contains:name=>this.classList.list.has(name),
  };
 }
 get textContent(){return this._text||this.children.map(c=>c.textContent??'').join('');}
 set textContent(value){this._text=String(value);this.children=[];}
 append(...nodes){for(const node of nodes){if(node&&typeof node==='object')node.parentNode=this;this.children.push(node);}}
 appendChild(node){this.append(node);return node;}
 replaceChildren(...nodes){this.children=[];this._text='';this.append(...nodes);}
 replaceWith(){}
 setAttribute(name,value){this.attributes[name]=String(value);}
 getAttribute(name){return this.attributes[name];}
 addEventListener(type,handler){this['on'+type]=handler;}
 removeEventListener(){}
 scrollIntoView(){}
 focus(){}
 closest(selector){
  let node=this;
  const name=selector.replace(/^\./,'');
  while(node){if(node.classList?.contains(name))return node;node=node.parentNode;}
  return new Element('div');
 }
 querySelectorAll(){return [];}
 querySelector(){return null;}
 get firstChild(){return this.children[0]||null;}
}
const registry=new Map();
const modeButtons=['board','custom','model'].map(mode=>{
 const button=new Element('button');button.dataset.mode=mode;return button;
});
globalThis.document={
 createElement:tag=>new Element(tag),
 getElementById:id=>{
  if(!registry.has(id)){
   if(!declared.has(id)){missing.push(id);}
   const entry=declared.get(id)||{tag:'div',value:''};
   const element=new Element(entry.tag);
   element.value=entry.value;
   registry.set(id,element);
  }
  return registry.get(id);
 },
 querySelectorAll:selector=>selector==='.scout-mode'?modeButtons:[],
};
const store=new Map();
globalThis.localStorage={
 getItem:key=>store.has(key)?store.get(key):null,
 setItem:(key,value)=>store.set(key,String(value)),
 removeItem:key=>store.delete(key),
};
globalThis.fetch=async url=>{
 const file=path.join('dist',String(url).replace(/^\.\//,''));
 if(!fs.existsSync(file))return {ok:false,status:404,json:async()=>({})};
 return {ok:true,status:200,json:async()=>JSON.parse(fs.readFileSync(file,'utf8'))};
};

const {createScout}=await import('../dist/scout.js');
const notices=[],opened=[];
const scout=createScout({notify:message=>notices.push(message),openInMatchroom:id=>opened.push(id)});

// ---- 1. Opening the view loads the models and fills the board.
await scout.show();
const $=id=>document.getElementById(id);
assert.deepEqual(missing,[],'scout.js reached for ids that index.html does not declare: '+missing.join(', '));
assert.equal($('scout-loading').hidden,true,'the loading note must be hidden once the models arrive');
assert.equal($('scout-board').hidden,false);
assert.ok($('scout-list').children.length>0,'the prospect board must render cards');
assert.match($('scout-pool-count').textContent,/under-21 seasons · \d+ nationalities/);
assert.ok(Number($('scout-nations').textContent)>60,'the headline nationality count must be populated');
assert.ok($('scout-region').children.length>=6,'every confederation should be filterable');
assert.ok($('scout-year').children.length>10,'every season should be filterable');
const modelFile=JSON.parse(fs.readFileSync('dist/scouting/model.json','utf8'));
console.log(`Board: ${$('scout-list').children.length} cards rendered, ${new Set(Object.values(modelFile.regions)).size} confederations, ${$('scout-year').children.length} seasons.`);

// ---- 2. Filters narrow the pool and selecting a prospect renders a full report.
$('scout-position').value='F';
$('scout-age').value='18';
$('scout-position').onchange();
const narrowed=$('scout-pool-count').textContent;
assert.notEqual(narrowed,'','filtering must update the count');
$('scout-position').value='all';$('scout-age').value='21';$('scout-position').onchange();

const firstCard=$('scout-list').children.find(child=>typeof child.onclick==='function');
assert.ok(firstCard,'cards must be clickable');
firstCard.onclick();
const report=$('scout-report');
const reportText=report.textContent;
assert.ok(report.children.length>4,'the report must render its blocks');
for(const fragment of ['Where they are listed next','Where players like this go next','Profiles like this','Closest archetype'])
 assert.ok(reportText.includes(fragment),`the report is missing "${fragment}"`);
assert.ok(reportText.includes(modelFile.progression.outcomes[0]),'the censoring class must be named in the report');
assert.ok(/fit share/.test(reportText),'fit rows must be rendered');
console.log('Report: identity, projection, club fits, archetype and comparables all rendered.');

// ---- 3. The fit rows hand club editions back to the Matchroom.
const findButtons=node=>node.children.flatMap(child=>
 child instanceof Element?[...(typeof child.onclick==='function'?[child]:[]),...findButtons(child)]:[]);
const buttons=findButtons(report);
const matchroom=buttons.find(button=>button.textContent.includes('Matchroom'));
assert.ok(matchroom,'a fit row must offer a Matchroom handoff');
matchroom.onclick();
assert.equal(opened.length,1,'the Matchroom handoff must fire');
assert.match(opened[0],/^(en|es|de|it|fr)-\d{4}-/,'the handoff must pass a club edition id');

// ---- 4. The watchlist round-trips through storage.
const watch=buttons.find(button=>button.textContent.includes('watchlist'));
assert.ok(watch,'the report must offer a watchlist action');
watch.onclick();
assert.ok(store.has('jogo.scout.v1'),'the watchlist must persist');
assert.equal(JSON.parse(store.get('jogo.scout.v1')).length,1);
assert.ok(notices.some(n=>/watchlist/i.test(n)),'saving must be acknowledged');
console.log(`Handoff and watchlist: ${opened[0]} sent to the Matchroom, one prospect stored locally.`);

// ---- 5. The custom prospect form scores a player the snapshot has never seen.
scout.show();
for(const button of modeButtons)if(button.dataset.mode==='custom')button.onclick();
assert.equal($('scout-custom').hidden,false);
assert.ok($('cp-club').children.length>0,'the club-edition picker must be populated');
assert.ok($('cp-nations').children.length>100,'the nationality list must come from the data');
$('cp-name').value='Academy Prospect';
$('cp-age').value='17';
$('cp-position').value='F';
$('cp-nationality').value='bra';
$('cp-level').value='band';
$('cp-level').onchange();
assert.equal($('cp-club-wrap').hidden,true,'a band reference must hide the club picker');
$('cp-run').onclick();
assert.equal($('cp-error').hidden,true,'a valid prospect must not error: '+$('cp-error').textContent);
const custom=$('scout-custom-report').textContent;
assert.ok(custom.includes('Academy Prospect'),'the custom report must name the player');
assert.ok(custom.includes('Where players like this go next')&&custom.includes('reference club'),'the band reference must be labelled');
assert.ok(custom.includes('Where they are listed next'));

// Invalid input is rejected rather than silently scored.
$('cp-age').value='40';
$('cp-run').onclick();
assert.equal($('cp-error').hidden,false,'an impossible age must be rejected');
assert.match($('cp-error').textContent,/age/i);
$('cp-age').value='17';
$('cp-nationality').value='BRAZIL';
$('cp-run').onclick();
assert.equal($('cp-error').hidden,false,'a malformed nationality code must be rejected');
$('cp-nationality').value='';
$('cp-level').value='club';
$('cp-level').onchange();
$('cp-club-search').value='barcelona';
$('cp-club-search').oninput();
assert.ok($('cp-club').children.length>0,'searching must find club editions');
$('cp-club').value=$('cp-club').children[0].value;
$('cp-run').onclick();
assert.equal($('cp-error').hidden,true,'a real club reference must score: '+$('cp-error').textContent);
console.log('Custom intake: band and club references both score, bad age and bad nationality both refused.');

// ---- 6. The model card publishes the held-out numbers, not just the method.
for(const button of modeButtons)if(button.dataset.mode==='model')button.onclick();
assert.equal($('scout-model').hidden,false);
const card=$('scout-model').textContent;
const model=modelFile;
for(const fragment of ['How these models were fitted','Club fit','Progression','What this cannot tell you','What the ranker learned',
 'Most-active clubs','Closest club level','Brier score',String(model.seed)])
 assert.ok(card.includes(fragment),`the model card is missing "${fragment}"`);
for(const limit of model.limits)assert.ok(card.includes(limit),'every declared limit must be shown');
assert.ok(card.includes(String(model.fit.metrics.model.median_rank)),'the median rank must be published');
console.log('Model card: baselines, calibration and every declared limit are published in the interface.');
