export function positionGroup(player){
 const p=String(player.position||'').toUpperCase();
 if(p==='G'||p==='GK'||p.includes('GOALKEEPER'))return 'G';
 if(p.startsWith('D'))return 'D';
 if(p.startsWith('M'))return 'M';
 return 'F';
}
export function suggestedXI(players){
 const available=players.filter(p=>p.status!=='departed');
 const chosen=[];
 for(const [group,count] of [['G',1],['D',4],['M',3],['F',3]])chosen.push(...available.filter(p=>positionGroup(p)===group&&!chosen.some(c=>c.id===p.id)).slice(0,count));
 for(const p of available){if(chosen.length>=11)break;if(positionGroup(p)!=='G'&&!chosen.some(c=>c.id===p.id))chosen.push(p);}
 return chosen;
}
export function lineupError(players){
 if(players.length!==11)return 'Select exactly 11 players.';
 if(new Set(players.map(p=>p.id)).size!==11)return 'The XI contains duplicate players.';
 if(players.filter(p=>positionGroup(p)==='G').length!==1)return 'Select exactly one goalkeeper.';
 if(players.some(p=>p.status==='departed'))return 'Departed players cannot be selected in this snapshot XI.';
 return null;
}
export function assignPlayer(events,players,random){
 for(const e of events){
  const pool=players.filter(p=>e.type!=='shot'||positionGroup(p)!=='G');
  if(!pool.length)continue;
  const weight=p=>e.type==='shot'?({D:1,M:3,F:6}[positionGroup(p)]||0):({G:1,D:4,M:6,F:3}[positionGroup(p)]||1);
  const sum=pool.reduce((n,p)=>n+weight(p),0);let pick=random()*sum;let player=pool[pool.length-1];
  for(const p of pool){pick-=weight(p);if(pick<0){player=p;break;}}
  e.player=player.name;e.player_id=player.id;
 }
}
