import assert from 'node:assert/strict';
import fs from 'node:fs';
import {snapshot,probabilities} from '../dist/engine.js';
const matches=JSON.parse(fs.readFileSync('dist/matches.json','utf8'));
for(const match of matches){
 assert.equal(snapshot(match,0).events.length,0);
 let previous=0;
 for(const minute of [0,15,45,58.25,75,90]){
  const state=snapshot(match,minute);
  assert.ok(state.events.length>=previous);previous=state.events.length;
  const p=probabilities(state.stats,minute);
  assert.ok(p.every(n=>Number.isFinite(n)&&n>=0&&n<=1));
  assert.ok(Math.abs(p.reduce((a,b)=>a+b,0)-1)<1e-10);
  for(const team of ['home','away'])assert.equal(state.stats[team].goals,state.events.filter(e=>e.team===team&&e.outcome==='goal').length);
 }
 const final=snapshot(match,90).stats;
 const expected=final.home.goals>final.away.goals?0:final.home.goals===final.away.goals?1:2;
 assert.equal(probabilities(final,90)[expected],1);
 assert.deepEqual(snapshot(match,45),snapshot(match,45));
}
console.log('Replay engine: 3 fixtures, timeline boundaries, scores, and probability invariants passed.');
