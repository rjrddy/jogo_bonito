import {assignPlayer,lineupError} from './squads.js';
// Historical team-edition baseline. All generated events are hypothetical.
export const MODEL_VERSION='historical-v2';
const clamp=(n,lo,hi)=>Math.max(lo,Math.min(hi,n));
export function randomGenerator(seed){
 let state=Number(seed)>>>0;
 return ()=>{state=(state+0x6D2B79F5)|0;let t=Math.imul(state^(state>>>15),1|state);t^=t+Math.imul(t^(t>>>7),61|t);return ((t^(t>>>14))>>>0)/4294967296;};
}
export function expectedGoals(home,away,venue='neutral'){
 if(!home||!away||![home.attack,home.defense,away.attack,away.defense].every(n=>Number.isFinite(n)&&n>0))throw new Error('Invalid team strengths');
 if(!['neutral','home'].includes(venue))throw new Error('Invalid venue');
 // Equal competition baselines are an explicit simplifying assumption.
 const base=1.35;
 return {home:clamp(base*home.attack*away.defense*(venue==='home'?1.12:1),.15,4.5),away:clamp(base*away.attack*home.defense*(venue==='home'?.92:1),.15,4.5)};
}
function poisson(lambda,random){let p=1,k=0,limit=Math.exp(-lambda);do{k++;p*=random();}while(p>limit);return k-1;}
export function simulate(home,away,{seed=202316,venue='neutral',lineups={}}={}){
 if(!Number.isInteger(Number(seed))||Number(seed)<0||Number(seed)>4294967295)throw new Error('Seed must be an integer from 0 to 4294967295');
 for(const side of ['home','away']){if(lineups[side]?.length){const error=lineupError(lineups[side]);if(error)throw new Error(side+': '+error);}}
 const rates=expectedGoals(home,away,venue),random=randomGenerator(seed);
 const id=`sim-${home.id}-${away.id}-${venue}-${Number(seed)}`;
 const events=[];
 for(const team of ['home','away']){
  const count=poisson(rates[team]/.15,random);
  for(let i=0;i<count;i++){
   const xg=.05+.2*random(), angle=random()*.9;
   const distance=clamp((2.1-.8*angle-Math.log(xg/(1-xg)))/.145,4,35);
   const outcome=random()<xg?'goal':random()<.5?'saved':random()<.5?'blocked':'off target';
   events.push({minute:Math.round((.05+random()*89.9)*1000)/1000,team,type:'shot',player:'Attacking unit',x:team==='home'?100-distance:distance,y:50+(random()-.5)*48,xg,outcome});
  }
 }
 const share=clamp(.5+.12*Math.log(rates.home/rates.away),.32,.68);
 const passes=560+Math.floor(random()*220);
 for(let i=0;i<passes;i++){
  const team=random()<share?'home':'away';
  events.push({minute:Math.round((.05+random()*89.9)*1000)/1000,team,type:'pass',player:'Team build-up',x:5+random()*90,y:5+random()*90,xg:0,outcome:random()<.86?'complete':'incomplete'});
 }
 events.sort((a,b)=>a.minute-b.minute);
 for(const [i,team] of ['home','away'].entries()){if(lineups[team]?.length)assignPlayer(events.filter(e=>e.team===team),lineups[team],randomGenerator((Number(seed)^(i?0xABCD1234:0x1234ABCD))>>>0));}
 events.forEach((e,i)=>{e.id=`${id}-${i}`;e.match_id=id;e.x=+e.x.toFixed(3);e.y=+e.y.toFixed(3);e.xg=+e.xg.toFixed(4);});
 return {id,home:home.name,away:away.name,home_edition:home,away_edition:away,rates,seed:Number(seed),venue,model:MODEL_VERSION,lineups,events};
}
export function outcomeDistribution(rates){
 const mass=lambda=>{const p=[Math.exp(-lambda)];for(let i=1;i<40;i++)p.push(p[i-1]*lambda/i);return p;};
 const h=mass(rates.home),a=mass(rates.away);const result=[0,0,0];
 h.forEach((p,i)=>a.forEach((q,j)=>result[i>j?0:i===j?1:2]+=p*q));
 return result;
}
