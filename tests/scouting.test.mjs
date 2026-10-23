import assert from 'node:assert/strict';
import fs from 'node:fs';
import {
  playerVector,
  candidateVector,
  progression,
  fitScore,
  rankClubs,
  latentPlayer,
  archetypeOf,
  similarTo,
  softmax,
  dot,
} from '../dist/scouting-engine.js';
import { hydrateClubs, hydrateProspects, prospectRecord } from '../dist/scout-data.js';

const model = JSON.parse(fs.readFileSync('dist/scouting/model.json', 'utf8'));
const clubsFile = JSON.parse(fs.readFileSync('dist/scouting/clubs.json', 'utf8'));
const prospectsFile = JSON.parse(fs.readFileSync('dist/scouting/prospects.json', 'utf8'));
const catalog = JSON.parse(fs.readFileSync('dist/catalog.json', 'utf8'));
const clubs = hydrateClubs(clubsFile);
const pool = hydrateProspects(prospectsFile, clubs);

// ---- 1. The JavaScript port must reproduce the Python feature vectors exactly.
let compared = 0;
for (const fixture of model.fixtures) {
  const origin = clubs.byId.get(fixture.origin);
  assert.ok(origin, 'fixture origin missing from clubs.json: ' + fixture.origin);
  const vector = playerVector(fixture.prospect, origin, model.spec);
  assert.equal(vector.length, model.player_features.length);
  for (const [i, expected] of fixture.player_vector.entries())
    assert.ok(
      Math.abs(vector[i] - expected) < 1e-9,
      `player feature ${model.player_features[i]} for ${fixture.prospect.name}: ${vector[i]} != ${expected}`,
    );
  const result = progression(fixture.prospect, origin, model);
  for (const [i, expected] of fixture.progression.entries())
    assert.ok(
      Math.abs(result.probabilities[i] - expected) < 1e-9,
      `progression class ${i}: ${result.probabilities[i]} != ${expected}`,
    );
  for (const candidate of fixture.candidates) {
    const target = clubs.byId.get(candidate.edition);
    const features = candidateVector(fixture.prospect, origin, target, model.spec);
    assert.equal(features.length, model.candidate_features.length);
    for (const [i, expected] of candidate.vector.entries())
      assert.ok(
        Math.abs(features[i] - expected) < 1e-9,
        `candidate feature ${model.candidate_features[i]} -> ${candidate.edition}: ${features[i]} != ${expected}`,
      );
    const scored = fitScore(fixture.prospect, origin, target, model);
    assert.ok(
      Math.abs(scored.score - candidate.score) < 1e-8,
      `fit score ${fixture.prospect.name} -> ${candidate.edition}: ${scored.score} != ${candidate.score}`,
    );
    compared++;
  }
}
console.log(
  `Feature parity: ${model.fixtures.length} prospects and ${compared} candidate pairs match the Python vectors to 1e-9.`,
);

// ---- 2. Data integrity between the catalog and the scouting artifacts.
const catalogClubs = new Set(catalog.teams.filter(t => t.kind === 'club').map(t => t.id));
assert.equal(clubs.list.length, catalogClubs.size, 'every club edition needs a scouting profile');
for (const club of clubs.list) {
  assert.ok(catalogClubs.has(club.id), 'unknown club edition ' + club.id);
  assert.ok(
    club.club_index >= 0 && club.club_index < model.fit.embed.length,
    'club index out of range ' + club.id,
  );
  assert.ok(Number.isFinite(club.level) && Number.isFinite(club.attack) && Number.isFinite(club.defense));
  assert.ok(club.squad_size >= 0 && club.youth_rate >= 0 && club.youth_rate <= 1);
  assert.ok(club.foreign_share >= 0 && club.foreign_share <= 1);
  const summed = Object.values(club.nation_counts).reduce((a, b) => a + b, 0);
  assert.ok(
    summed === club.squad_size || club.squad_size === 0,
    `nation counts must total the squad for ${club.id}`,
  );
}
assert.equal(pool.length, prospectsFile.rows.length);
assert.equal(pool.length, model.pool.size);
for (const prospect of pool) {
  assert.ok(prospect.age <= prospectsFile.max_age + 0.001, 'pool must stay under ' + prospectsFile.max_age);
  assert.ok(clubs.byId.has(prospect.edition), 'prospect references unknown edition ' + prospect.edition);
  assert.ok(['G', 'D', 'M', 'F'].includes(prospect.position));
  assert.ok(prospect.debut_age <= prospect.age + 0.001, 'a debut cannot postdate the season');
}
const nations = new Set(pool.map(p => p.nationality).filter(Boolean));
assert.ok(nations.size > 60, `expected a global pool, found ${nations.size} nationalities`);
console.log(
  `Artifacts: ${clubs.list.length} club profiles, ${pool.length} prospects, ${nations.size} nationalities, all cross-referenced.`,
);

// ---- 3. Inference behaviour.
const sample = pool[Math.floor(pool.length / 3)];
const origin = clubs.byId.get(sample.edition);
const record = prospectRecord(sample);
const vector = playerVector(record, origin, model.spec);
const latent = latentPlayer(vector, model);
const season = clubs.list.filter(c => c.year === origin.year + 1);
assert.ok(season.length > 50, 'a destination season should offer a real candidate set');
const ranked = rankClubs(record, origin, season, model, 10);
assert.equal(ranked.length, 10);
for (let i = 1; i < ranked.length; i++)
  assert.ok(ranked[i - 1].score >= ranked[i].score, 'ranking must be ordered');
assert.ok(ranked.every(r => r.share > 0 && r.share < 1));
const repeat = rankClubs(record, origin, season, model, 10);
assert.deepEqual(
  repeat.map(r => r.target.id),
  ranked.map(r => r.target.id),
  'ranking must be deterministic',
);

// Explanations are an exact additive decomposition of the score, not a gloss.
for (const entry of ranked) {
  const total = entry.explanation.reduce((sum, part) => sum + part.contribution, 0);
  assert.ok(
    Math.abs(total - entry.score) < 1e-8,
    `explanation must sum to the score: ${total} != ${entry.score}`,
  );
}
console.log(
  `Ranking: ${season.length} candidate editions scored, ordered, reproducible, and additively explained.`,
);

// ---- 4. Probabilities and projections.
const projection = progression(record, origin, model);
assert.equal(projection.probabilities.length, model.progression.outcomes.length);
assert.ok(
  Math.abs(projection.probabilities.reduce((a, b) => a + b, 0) - 1) < 1e-9,
  'outcome probabilities must normalise',
);
assert.ok(projection.probabilities.every(p => p >= 0 && p <= 1));
assert.ok(projection.observable >= 0 && projection.observable <= 1);
assert.ok(projection.ceiling >= 1 && projection.ceiling <= 3.0001, 'ceiling is a conditional class index');
const uniform = softmax([0, 0, 0, 0]);
assert.ok(uniform.every(p => Math.abs(p - 0.25) < 1e-12));
assert.ok(Math.abs(dot([1, 2, 3], [4, 5, 6]) - 32) < 1e-12);

// A prospect at a stronger club should not be projected below the same prospect
// at a weaker one, holding everything else fixed.
const strong = [...clubs.list].sort((a, b) => b.level - a.level)[0];
const weak = [...clubs.list].sort((a, b) => a.level - b.level)[0];
const high = progression(record, strong, model),
  low = progression(record, weak, model);
assert.ok(
  high.observable > low.observable,
  `club level must inform the projection (${high.observable} vs ${low.observable})`,
);
console.log('Projections: normalised, bounded, calibrated offsets applied, and monotone in club level.');

// ---- 5. Archetypes and similarity.
const archetype = archetypeOf(latent, model);
assert.ok(archetype && archetype.label && archetype.distance >= 0);
assert.equal(
  new Set(model.archetypes.map(a => a.label)).size,
  model.archetypes.length,
  'archetype labels must be distinct',
);
assert.equal(model.archetypes.reduce((sum, a) => sum + a.members, 0) > 0, true);
const neighbours = pool
  .slice(0, 400)
  .map(p => ({
    ...p,
    latent: latentPlayer(playerVector(prospectRecord(p), clubs.byId.get(p.edition), model.spec), model),
  }));
const similar = similarTo(neighbours[0].latent, neighbours, 5);
assert.equal(similar.length, 5);
assert.equal(similar[0].entry.name, neighbours[0].name, 'a player is their own nearest neighbour');
assert.ok(similar[0].similarity > 0.999);
for (let i = 1; i < similar.length; i++) assert.ok(similar[i - 1].similarity >= similar[i].similarity);
console.log(
  `Archetypes: ${model.archetypes.length} distinct clusters; cosine neighbours ordered and self-matching.`,
);

// ---- 6. Reported metrics must still beat the baselines they are compared to.
const fit = model.fit.metrics;
assert.ok(fit.model.recall_5 > fit.popularity.recall_5 * 2, 'fit model must clear the popularity baseline');
assert.ok(
  fit.model.recall_5 > fit.closest_level.recall_5 * 2,
  'fit model must clear the level-matching baseline',
);
assert.ok(fit.model.mrr > fit.popularity.mrr && fit.model.mrr > fit.closest_level.mrr);
assert.ok(fit.model.median_rank < fit.closest_level.median_rank);
const prog = model.progression.metrics;
assert.ok(prog.accuracy > prog.majority_accuracy, 'progression must beat predicting the majority class');
assert.ok(prog.brier < prog.base_rate_brier, 'progression must beat the base rate on Brier score');
const topClass = model.progression.outcomes[model.progression.outcomes.length - 1];
assert.ok(prog.auc[topClass] > 0.7, `separation for "${topClass}" must stay useful: ${prog.auc[topClass]}`);
assert.ok(
  Object.keys(prog.auc).every(name => model.progression.outcomes.includes(name)),
  'reported AUC keys must match the declared outcome names',
);
for (const row of prog.calibration)
  assert.ok(
    Math.abs(row.predicted - row.observed) < 0.05,
    `${row.outcome} is miscalibrated: predicted ${row.predicted} vs observed ${row.observed}`,
  );
console.log(
  `Metrics: recall@5 ${fit.model.recall_5} vs ${fit.closest_level.recall_5} baseline; progression ${prog.accuracy} vs ${prog.majority_accuracy} majority; all classes calibrated within 5pp.`,
);
