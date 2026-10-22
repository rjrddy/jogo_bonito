import {playerVector,progression,rankClubs,latentPlayer,archetypeOf,similarTo,REASONS,
        POSITION_NAMES,COMPETITION_NAMES} from './scouting-engine.js';
import {hydrateClubs,hydrateProspects,prospectRecord} from './scout-data.js';
const $=id=>document.getElementById(id);
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
const pct=n=>(n*100).toFixed(n>=0.1?0:1)+'%';
const WATCHLIST='jogo.scout.v1';

// Everything here runs on data the browser already has; nothing is fetched per
// prospect. The three model files load once, the first time this view opens.
export function createScout({openInMatchroom,notify}){
 let model,clubs,pool,mode='board',selected=null,watchOnly=false,booted=null;
 let latents=[],elite=[],observable=[],neighbours=[];
 let refreshWatchButton=()=>{};
 const text=(id,value)=>{$(id).textContent=value;};

 async function boot(){
  const files=await Promise.all(['model','clubs','prospects'].map(async name=>{
   const response=await fetch(`./scouting/${name}.json`);
   if(!response.ok)throw new Error(`Scouting data could not be loaded (${name}.json). Reload to retry.`);
   return response.json();
  }));
  model=files[0];
  clubs=hydrateClubs(files[1]);
  pool=hydrateProspects(files[2],clubs);
  // One pass over the pool: the latent vector and projection every view needs.
  for(const prospect of pool){
   const club=clubs.byId.get(prospect.edition);
   const vector=playerVector(prospectRecord(prospect),club,model.spec);
   latents.push(latentPlayer(vector,model));
   const projection=progression(prospectRecord(prospect),club,model);
   elite.push(projection.probabilities[projection.probabilities.length-1]);
   observable.push(projection.observable);
  }
  // Built once: the similarity search reads this on every report.
  neighbours=pool.map((prospect,index)=>({...prospect,latent:latents[index]}));
  buildControls();
 }

 function buildControls(){
  const regions=[...new Set(Object.values(model.regions))].sort();
  $('scout-region').append(...regions.map(name=>Object.assign(document.createElement('option'),{value:name,textContent:name})));
  $('scout-competition').append(...Object.entries(COMPETITION_NAMES).map(([code,name])=>
   Object.assign(document.createElement('option'),{value:code,textContent:name})));
  const years=[...new Set(pool.map(p=>clubs.byId.get(p.edition).year))].sort((a,b)=>b-a);
  $('scout-year').append(...years.map(y=>Object.assign(document.createElement('option'),{value:String(y),textContent:y})));
  $('cp-nations').append(...Object.keys(model.nations).sort().map(code=>
   Object.assign(document.createElement('option'),{value:code})));
  text('scout-nations',String(new Set(pool.map(p=>p.nationality).filter(Boolean)).size));
  for(const id of ['scout-search','scout-position','scout-region','scout-competition','scout-year','scout-age','scout-sort'])
   $(id).addEventListener(id==='scout-search'?'input':'change',renderBoard);
  const watch=el('button','outline scout-watch-toggle');
  watch.type='button';
  watch.onclick=()=>{watchOnly=!watchOnly;watch.classList.toggle('active',watchOnly);renderBoard();};
  $('scout-search').closest('.scout-filters').append(watch);
  refreshWatchButton=()=>{watch.textContent=`☆ Watchlist (${readWatchlist().length})`;watch.classList.toggle('active',watchOnly);};
  refreshWatchButton();
  buildCustomForm();
  renderModelCard();
 }

 function readWatchlist(){
  try{const rows=JSON.parse(localStorage.getItem(WATCHLIST)||'[]');return Array.isArray(rows)?rows.filter(n=>Number.isInteger(n)&&n>=0&&n<pool.length):[];}
  catch{return [];}
 }
 function writeWatchlist(rows){
  try{localStorage.setItem(WATCHLIST,JSON.stringify(rows.slice(0,40)));refreshWatchButton();return true;}
  catch{notify('Browser storage is unavailable, so the watchlist cannot be kept.');return false;}
 }

 function flag(code){
  const path=model.flags[code];
  if(!path)return el('span','nation-chip',code||'—');
  const image=el('img','nation-flag');
  image.src=path;image.alt=code;image.width=20;image.height=15;
  image.onerror=()=>image.replaceWith(el('span','nation-chip',code));
  return image;
 }
 function crest(club,size=34){
  if(!club.crest){const initials=el('span','fallback-crest scout-crest',club.name.split(/\s+/).map(w=>w[0]).slice(0,3).join(''));return initials;}
  const image=el('img','scout-crest');
  image.src=club.crest;image.alt='';image.width=size;image.height=Math.round(size*1.12);
  image.onerror=()=>image.replaceWith(el('span','fallback-crest scout-crest',club.name.split(/\s+/).map(w=>w[0]).slice(0,3).join('')));
  return image;
 }

 // ---- Prospect board
 function filtered(){
  const query=$('scout-search').value.trim().toLocaleLowerCase();
  const position=$('scout-position').value,region=$('scout-region').value;
  const competition=$('scout-competition').value,year=$('scout-year').value;
  const maxAge=Number($('scout-age').value),watch=new Set(watchOnly?readWatchlist():[]);
  const rows=[];
  for(const prospect of pool){
   if(watchOnly&&!watch.has(prospect.index))continue;
   if(prospect.age>maxAge)continue;
   if(position!=='all'&&prospect.position!==position)continue;
   if(region!=='all'&&model.regions[prospect.nationality]!==region)continue;
   const club=clubs.byId.get(prospect.edition);
   if(competition!=='all'&&club.competition!==competition)continue;
   if(year!=='all'&&String(club.year)!==year)continue;
   if(query&&!`${prospect.name} ${club.name} ${prospect.nationality||''}`.toLocaleLowerCase().includes(query))continue;
   rows.push(prospect);
  }
  const sort=$('scout-sort').value;
  const compare={
   elite:(a,b)=>elite[b.index]-elite[a.index],
   observable:(a,b)=>observable[b.index]-observable[a.index],
   age:(a,b)=>a.age-b.age||elite[b.index]-elite[a.index],
   name:(a,b)=>a.name.localeCompare(b.name),
  }[sort];
  rows.sort(compare);
  return rows;
 }

 function renderBoard(){
  const rows=filtered(),root=$('scout-list');
  text('scout-pool-count',`${rows.length.toLocaleString()} of ${pool.length.toLocaleString()} under-${model.pool.max_age} seasons · ${new Set(rows.map(r=>r.nationality).filter(Boolean)).size} nationalities`);
  root.replaceChildren();
  if(!rows.length){root.append(el('p','empty-state','No prospect matches these filters.'));return;}
  for(const prospect of rows.slice(0,150)){
   const club=clubs.byId.get(prospect.edition);
   const card=el('button','scout-card'+(selected&&selected.index===prospect.index?' active':''));
   card.type='button';card.setAttribute('role','listitem');
   const head=el('div','scout-card-head');
   head.append(flag(prospect.nationality),el('strong','',prospect.name),el('span','scout-age',`${prospect.age}`));
   const meta=el('div','scout-card-meta');
   meta.append(el('span','',`${POSITION_NAMES[prospect.position]} · ${club.name}`),el('span','',club.year));
   const track=el('div','scout-card-track');
   const bar=el('b');bar.style.width=(elite[prospect.index]*100).toFixed(1)+'%';
   track.append(bar);
   card.append(head,meta,track,el('small','scout-card-score',`${pct(elite[prospect.index])} elite-club projection`));
   card.onclick=()=>{selected=prospect;renderBoard();renderReport(prospect,$('scout-report'));};
   root.append(card);
  }
  if(rows.length>150)root.append(el('p','lab-footnote',`Showing the first 150 of ${rows.length.toLocaleString()}. Narrow the filters to see further down the list.`));
 }

 // ---- Fit ranking, shared by the board and the custom form
 function fitFor(record,origin,scope,limit=12){
  const targets=(scope==='next'
   ?(clubs.byYear.get(origin.year+1)||clubs.byYear.get(origin.year)||[])
   :clubs.list).filter(club=>club.club!==origin.club);
  if(!targets.length)return {entries:[],targets};
  const ranked=rankClubs(record,origin,targets,model,targets.length);
  const best=new Map();
  for(const entry of ranked)if(!best.has(entry.target.club))best.set(entry.target.club,entry);
  const grouped=[...best.values()];
  const total=grouped.reduce((sum,entry)=>sum+entry.share,0)||1;
  return {entries:grouped.slice(0,limit).map(entry=>({...entry,share:entry.share/total})),targets,clubs:grouped.length};
 }

 function reasonList(entry){
  const list=el('div','fit-reasons');
  for(const part of entry.explanation.slice(0,4)){
   const chip=el('span','fit-reason'+(part.contribution>0?' positive':' negative'));
   chip.append(el('b','',part.label),el('i','',(part.contribution>0?'+':'')+part.contribution.toFixed(2)));
   chip.title=part.value===null?`${part.label}: ${part.contribution.toFixed(3)} added to the fit score`
    :`${part.label}: feature ${part.value.toFixed(3)} × weight = ${part.contribution.toFixed(3)}`;
   list.append(chip);
  }
  return list;
 }

 function renderReport(prospect,root,options={}){
  const club=options.overrideClub||clubs.byId.get(prospect.edition);
  const record=options.record||prospectRecord(prospect);
  const scope=options.scope||'next';
  const vector=playerVector(record,club,model.spec);
  const latent=latentPlayer(vector,model);
  const projection=progression(record,club,model);
  const archetype=archetypeOf(latent,model);
  root.replaceChildren();

  const header=el('div','scout-report-head');
  const identity=el('div','scout-identity');
  identity.append(flag(prospect.nationality),el('h3','',prospect.name||'Unnamed prospect'));
  const line=el('p','scout-identity-meta');
  line.textContent=`${prospect.age} years · ${POSITION_NAMES[prospect.position]}${prospect.number?` · number ${prospect.number}`:''} · ${prospect.nationality||'nationality unknown'}`;
  identity.append(line);
  const current=el('div','scout-current-club');
  current.append(crest(club,40));
  const where=el('div');
  where.append(el('strong','',club.name),el('span','',`${club.competition_name||COMPETITION_NAMES[club.competition]} ${club.year}`));
  current.append(where);
  header.append(identity,current);
  root.append(header);
  if(archetype)root.append(el('p','scout-archetype',`Closest archetype in the learned space: ${archetype.label}.`));

  // Projection
  const projectionPanel=el('div','scout-block');
  projectionPanel.append(el('h4','','Where they are listed next'));
  projectionPanel.append(el('p','scout-block-note',`Which calibre of squad list a player first seen at this age and level appears on, from ${model.progression.metrics.settle+1} to ${model.progression.metrics.horizon} seasons later. A squad list records who a club registered, not who played, so this is where a career is listed — not how good it became.`));
  const bars=el('div','outcome-bars');
  projection.outcomes.forEach((outcome,index)=>{
   const row=el('div','outcome-row');
   row.dataset.outcome=String(index);
   const track=el('span','outcome-track');
   const fill=el('b');fill.style.width=(outcome.probability*100).toFixed(1)+'%';
   track.append(fill);
   row.append(el('span','outcome-label',outcome.label),track,el('strong','',pct(outcome.probability)));
   bars.append(row);
  });
  projectionPanel.append(bars);
  projectionPanel.append(el('p','lab-footnote',`“No further top-five squad” is censoring, not failure: a move to a league outside these five looks the same in this data. Being at a strong club already is the single biggest driver here, so the highest projections sit on big-club academy intakes almost by construction. Held-out accuracy ${pct(model.progression.metrics.accuracy)} against ${pct(model.progression.metrics.majority_accuracy)} for always predicting the most common outcome.`));
  if(prospect.outcome!==null&&prospect.outcome!==undefined){
   const truth=el('p','scout-truth');
   const peak=prospect.peak_edition?clubs.byId.get(prospect.peak_edition):null;
   truth.append(el('b','','WHAT THE SNAPSHOT RECORDS: '),document.createTextNode(
    `${model.progression.outcomes[prospect.outcome]}${peak?` · peak squad ${peak.name} ${peak.year}`:''}`));
   projectionPanel.append(truth);
  }else if(!options.custom){
   projectionPanel.append(el('p','scout-truth',`This player's six-season window runs past the ${model.as_of} cutoff, so no outcome is recorded yet.`));
  }
  root.append(projectionPanel);

  // Club fit
  const fit=fitFor(record,club,scope);
  const fitPanel=el('div','scout-block');
  fitPanel.append(el('h4','','Where players like this go next'));
  fitPanel.append(el('p','scout-block-note',scope==='next'
   ?`Ranked across the ${fit.targets.length} club editions of the following season, excluding their current club.`
   :`Closest-matching edition of each of ${fit.clubs||0} club identities, every era considered.`));
  fitPanel.append(el('p','scout-block-note','This ranks the destinations players with this profile were actually recorded moving to. The source cannot separate a loan from a transfer, so for a teenager at a strong club the likeliest next club is often a smaller one — the model is reporting the market, not naming who ought to sign them.'));
  for(const entry of fit.entries){
   const row=el('article','fit-row');
   row.append(crest(entry.target,30));
   const body=el('div','fit-body');
   const head=el('div','fit-head');
   head.append(el('strong','',entry.target.name),el('span','',`${COMPETITION_NAMES[entry.target.competition]} ${entry.target.year}`));
   body.append(head,reasonList(entry));
   const share=el('div','fit-share');
   share.append(el('strong','',pct(entry.share)),el('small','','fit share'));
   const open=el('button','outline','Matchroom ↗');
   open.onclick=()=>openInMatchroom(entry.target.id);
   open.title=`Load ${entry.target.name} ${entry.target.year} as the home side`;
   row.append(body,share,open);
   fitPanel.append(row);
  }
  if(!fit.entries.length)fitPanel.append(el('p','empty-state','No destination season is available for this edition.'));
  fitPanel.append(el('p','lab-footnote',`Fit is learned from ${model.fit.metrics.train_moves.toLocaleString()} real club-to-club moves, so it reflects the recruitment market rather than merit. On held-out later seasons the true destination lands in the top five of about ${fit.targets.length} candidates ${pct(model.fit.metrics.model.recall_5)} of the time, against ${pct(model.fit.metrics.closest_level.recall_5)} for ranking by closest club level. Shares are a split of this shortlist, not a probability that any transfer happens.`));
  root.append(fitPanel);

  // Comparable prospects
  if(!options.custom||options.compare!==false){
   const matches=similarTo(latent,neighbours,options.custom?7:8)
    .filter(match=>options.custom||match.entry.index!==prospect.index).slice(0,6);
   const comparePanel=el('div','scout-block');
   comparePanel.append(el('h4','','Profiles like this'));
   comparePanel.append(el('p','scout-block-note','Nearest prospects by cosine similarity in the fit model’s learned player space. A shared profile is not a shared ability.'));
   const list=el('div','compare-list');
   for(const match of matches){
    const other=match.entry,otherClub=clubs.byId.get(other.edition);
    const card=el('button','compare-card');card.type='button';
    card.append(flag(other.nationality),el('strong','',other.name),
     el('span','',`${otherClub.name} ${otherClub.year} · ${other.age}`),
     el('small','',`${(match.similarity*100).toFixed(1)}% profile match${other.outcome!==null&&other.outcome!==undefined?` · ${model.progression.outcomes[other.outcome].toLowerCase()}`:''}`));
    card.onclick=()=>{selected=other;setMode('board');renderBoard();renderReport(other,$('scout-report'));$('scout-report').scrollIntoView({block:'start',behavior:'smooth'});};
    list.append(card);
   }
   comparePanel.append(list);
   root.append(comparePanel);
  }

  // Actions
  const actions=el('div','scout-actions');
  if(!options.custom){
   const watchlist=readWatchlist();
   const saved=watchlist.includes(prospect.index);
   const save=el('button','outline',saved?'★ On your watchlist':'☆ Add to watchlist');
   save.onclick=()=>{
    const rows=readWatchlist();
    const next=rows.includes(prospect.index)?rows.filter(i=>i!==prospect.index):[prospect.index,...rows];
    if(writeWatchlist(next)){notify(rows.includes(prospect.index)?'Removed from your watchlist.':'Added to your watchlist, in this browser only.');renderReport(prospect,root,options);renderBoard();}
   };
   actions.append(save);
  }
  const home=el('button','outline','Open their club in the Matchroom ↗');
  home.onclick=()=>openInMatchroom(club.id);
  actions.append(home);
  root.append(actions);
  root.append(el('p','source-credit',`Squad snapshot: FootballSquads. Club profile for ${club.name} ${club.year} describes the squad and results of ${club.profile_source}${club.profile_fallback?' (no earlier season available, so its own season is used)':''}.`));
 }

 // ---- Custom prospect
 function buildCustomForm(){
  const search=$('cp-club-search'),select=$('cp-club');
  function populate(){
   const query=search.value.trim().toLocaleLowerCase();
   const matches=clubs.list.filter(club=>!query||`${club.name} ${club.year}`.toLocaleLowerCase().includes(query))
    .sort((a,b)=>a.name.localeCompare(b.name)||b.year-a.year).slice(0,60);
   select.replaceChildren(...matches.map(club=>Object.assign(document.createElement('option'),
    {value:club.id,textContent:`${club.name} ${club.year} · ${COMPETITION_NAMES[club.competition]}`})));
   if(!matches.length)select.append(Object.assign(document.createElement('option'),{value:'',textContent:'No club edition matches'}));
  }
  search.oninput=populate;
  const mode=$('cp-level');
  const sync=()=>{$('cp-club-wrap').hidden=mode.value!=='club';$('cp-band-wrap').hidden=mode.value!=='band';};
  mode.onchange=sync;sync();populate();
  $('cp-run').onclick=runCustom;
 }

 // A band is a stand-in for a real club: the median club edition at that
 // strength quartile, which is an assumption and is labelled as one.
 function bandProfile(band){
  const sorted=[...clubs.list].sort((a,b)=>a.level-b.level);
  const share=[0.15,0.4,0.65,0.9][Math.min(3,Math.max(0,Number(band)-1))];
  const club=sorted[Math.floor(share*(sorted.length-1))];
  return {...club,name:`${['Lower-table','Mid-table','Continental-level','Elite'][Number(band)-1]} reference club`,
   id:club.id,crest:null};
 }

 function runCustom(){
  const error=message=>{text('cp-error',message);$('cp-error').hidden=false;};
  try{
   const age=Number($('cp-age').value);
   if(!Number.isFinite(age)||age<14||age>23)throw new Error('Enter an age between 14 and 23.');
   const nationality=$('cp-nationality').value.trim().toUpperCase();
   if(nationality&&!/^[A-Z]{3}$/.test(nationality))throw new Error('Use a three-letter nationality code, or leave it blank.');
   const numberValue=$('cp-number').value.trim();
   const club=$('cp-level').value==='club'
    ?clubs.byId.get($('cp-club').value)
    :bandProfile($('cp-band').value);
   if(!club)throw new Error('Choose a club edition to use as the current level.');
   const record={
    name:$('cp-name').value.trim()||'Your prospect',
    age,position:$('cp-position').value,nationality:nationality||null,
    number:numberValue===''?null:Number(numberValue),
    years_at_club:Number($('cp-years').value||0),
    seasons_seen:Number($('cp-seasons').value||1),
    debut_age:age-Math.max(0,Number($('cp-seasons').value||1)-1),
    foreign:nationality&&model.regions[nationality]?(club.competition&&!homeCodes(club.competition).includes(nationality)?1:0):1,
    status:'listed',
   };
   $('cp-error').hidden=true;
   const display={...record,index:-1,edition:club.id,nationality:record.nationality,outcome:null,peak_edition:null,
    departed:0,identity:-1};
   renderReport(display,$('scout-custom-report'),{record,custom:true,scope:$('cp-era').value,
    overrideClub:club});
   if(!model.nations[record.nationality]&&record.nationality)
    notify(`${record.nationality} does not appear in the bundled squads, so the nationality features fall back to an empty pool.`);
  }catch(e){error(e.message);}
 }
 const homeCodes=competition=>({en:['ENG','WAL','SCO','NIR'],es:['ESP'],de:['GER'],it:['ITA'],fr:['FRA']}[competition]||[]);

 // ---- Model card
 function renderModelCard(){
  const root=$('scout-model');root.replaceChildren();
  const fit=model.fit.metrics,prog=model.progression.metrics;
  const intro=el('section','panel');
  intro.append(el('h3','','How these models were fitted'));
  intro.append(el('p','scout-block-note',model.method));
  const facts=el('div','model-facts');
  for(const [label,value] of [
   ['Prospect pool',`${model.pool.size.toLocaleString()} under-${model.pool.max_age} club seasons`],
   ['Distinct players',model.pool.identities.toLocaleString()],
   ['Outcomes observable',`${model.pool.labelled.toLocaleString()} of ${model.pool.size.toLocaleString()}`],
   ['Moves used for fit',fit.train_moves.toLocaleString()],
   ['Latent dimensions',fit.latent],
   ['Snapshot cutoff',model.as_of],
  ]){const cell=el('div');cell.append(el('span','',label),el('strong','',String(value)));facts.append(cell);}
  intro.append(facts);
  root.append(intro);

  const fitPanel=el('section','panel');
  fitPanel.append(el('h3','','Club fit: ranking the true destination'));
  fitPanel.append(el('p','scout-block-note',`Validation uses every observed move from ${fit.validation_from} onwards, seasons the weights never saw. Each move is ranked against the roughly ${fit.candidates_mean} club editions available that season. Baselines face the identical task.`));
  const table=el('table'),head=el('thead'),headRow=el('tr');
  for(const label of ['','TOP 1','TOP 5','TOP 10','TOP 25','MRR','MEDIAN RANK'])headRow.append(el('th','',label));
  head.append(headRow);table.append(head);
  const body=el('tbody');
  for(const [label,metrics] of [['This model',fit.model],['Most-active clubs',fit.popularity],['Closest club level',fit.closest_level]]){
   const row=el('tr');
   if(label==='This model')row.className='model-row';
   row.append(el('td','',label));
   for(const value of [metrics.recall_1,metrics.recall_5,metrics.recall_10,metrics.recall_25])row.append(el('td','',pct(value)));
   row.append(el('td','',metrics.mrr.toFixed(3)),el('td','',String(metrics.median_rank)));
   body.append(row);
  }
  table.append(body);
  const wrap=el('div','table-wrap');wrap.append(table);fitPanel.append(wrap);
  fitPanel.append(el('p','lab-footnote',`n = ${fit.model.n.toLocaleString()} held-out moves. Trained on one true destination against ${fit.negatives} sampled alternatives. The model has no fitted view on a player staying put: it only ever saw moves, so the "already at this club" term keeps a zero weight.`));
  root.append(fitPanel);

  const learned=el('section','panel');
  learned.append(el('h3','','What the ranker learned'));
  learned.append(el('p','scout-block-note','Fitted weights on the named player x club terms, largest first. These are the whole of the explainable part of a fit score; the rest is the latent style term and the club profile.'));
  const weightTable=el('table'),weightHead=el('thead'),weightRow=el('tr');
  for(const label of ['TERM','WEIGHT','READS AS'])weightRow.append(el('th','',label));
  weightHead.append(weightRow);weightTable.append(weightHead);
  const weightBody=el('tbody');
  const terms=model.candidate_features.slice(model.cross_offset)
   .map((key,index)=>({key,weight:model.fit.weights[model.cross_offset+index]}))
   .sort((a,b)=>Math.abs(b.weight)-Math.abs(a.weight));
  for(const term of terms){
   const row=el('tr');
   row.append(el('td','',REASONS[term.key]||term.key),el('td','',term.weight.toFixed(3)),
    el('td','',term.weight===0?'never varied in training'
     :term.weight>0?'raises the fit score':'lowers the fit score'));
   weightBody.append(row);
  }
  weightTable.append(weightBody);
  const weightWrap=el('div','table-wrap');weightWrap.append(weightTable);
  learned.append(weightWrap);
  learned.append(el('p','lab-footnote','A gap at the prospect’s position and compatriots already in the squad dominate, which says as much about how recruitment works as about the players. The level terms are negative and the young-step-up term positive: large jumps are rare, and rarer still except for the youngest players.'));
  root.append(learned);

  const progPanel=el('section','panel');
  progPanel.append(el('h3','','Progression: the six-season outcome'));
  progPanel.append(el('p','scout-block-note',`Cohorts up to ${prog.validation_from-3} fit the weights, ${prog.validation_from-2}–${prog.validation_from-1} fit the class priors, and ${prog.validation_from} onwards is held out. Tier boundaries come from the training split only.`));
  const metrics=el('div','model-facts');
  for(const [label,value] of [
   ['Accuracy',`${pct(prog.accuracy)} vs ${pct(prog.majority_accuracy)} majority`],
   ['Brier score',`${prog.brier} vs ${prog.base_rate_brier} base rate`],
   ['Before recalibration',String(prog.uncalibrated_brier)],
   ['Training cohorts',prog.train.toLocaleString()],
   ['Held-out cohorts',prog.validation.toLocaleString()],
  ]){const cell=el('div');cell.append(el('span','',label),el('strong','',String(value)));metrics.append(cell);}
  progPanel.append(metrics);
  const calibration=el('table'),calibrationHead=el('thead'),calibrationRow=el('tr');
  for(const label of ['OUTCOME','AUC','PREDICTED','OBSERVED'])calibrationRow.append(el('th','',label));
  calibrationHead.append(calibrationRow);calibration.append(calibrationHead);
  const calibrationBody=el('tbody');
  for(const row of prog.calibration){
   const tr=el('tr');
   tr.append(el('td','',row.outcome),el('td','',prog.auc[row.outcome].toFixed(3)),
    el('td','',pct(row.predicted)),el('td','',pct(row.observed)));
   calibrationBody.append(tr);
  }
  calibration.append(calibrationBody);
  const calibrationWrap=el('div','table-wrap');calibrationWrap.append(calibration);
  progPanel.append(calibrationWrap);
  progPanel.append(el('p','lab-footnote','AUC near 0.5 means that class is barely separable; the middle tiers are the hard ones and the table says so. Predicted and observed columns are the held-out cohorts.'));
  root.append(progPanel);

  const limits=el('section','panel');
  limits.append(el('h3','','What this cannot tell you'));
  const list=el('ul','scout-limits');
  for(const limit of model.limits)list.append(el('li','',limit));
  for(const limit of [
   'There is no academy data here. The pool is the under-21 players in the bundled senior-squad snapshots, which is the youngest cohort this repository can observe, not a youth-team intake.',
   'A hand-entered prospect is scored from the attributes you supply. The model has no way to verify them.',
   'Positions come from the source listing, and no minutes, fees or valuations exist in this data at all.',
   `Archetypes are k-means clusters over the fit model's latent space, named from their members' own averages.`,
  ])list.append(el('li','',limit));
  limits.append(list);
  limits.append(el('p','source-credit',`Models rebuilt by scripts/build_scouting.py with seed ${model.seed}. Source: ${model.source}.`));
  root.append(limits);
 }

 function setMode(next){
  mode=next;
  for(const button of document.querySelectorAll('.scout-mode')){
   const active=button.dataset.mode===next;
   button.classList.toggle('active',active);
   button.setAttribute('aria-selected',String(active));
  }
  $('scout-board').hidden=next!=='board';
  $('scout-custom').hidden=next!=='custom';
  $('scout-model').hidden=next!=='model';
 }

 async function show(){
  if(!booted){
   booted=boot().catch(e=>{booted=null;throw e;});
   try{await booted;}
   catch(e){$('scout-loading').textContent=e.message;return;}
   $('scout-loading').hidden=true;
   for(const button of document.querySelectorAll('.scout-mode'))button.onclick=()=>setMode(button.dataset.mode);
   setMode('board');
   renderBoard();
   return;
  }
  await booted;
  setMode(mode);
 }
 return {show};
}
