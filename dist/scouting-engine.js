// Browser-side inference for the offline-trained scouting models.
// The two vector builders below are a line-for-line port of
// scripts/scouting_features.py. tests/scouting.test.mjs replays the fixtures
// baked into scouting/model.json through this file and fails on any drift, so
// treat the Python module as the specification and keep the arithmetic identical.
const POSITIONS = ['G', 'D', 'M', 'F'];
export const POSITION_SHARE = { G: 1 / 11, D: 4 / 11, M: 4 / 11, F: 2 / 11 };
export const POSITION_NAMES = { G: 'Goalkeeper', D: 'Defender', M: 'Midfielder', F: 'Forward' };
const COMPETITIONS = ['en', 'es', 'de', 'it', 'fr'];
export const COMPETITION_NAMES = {
  en: 'Premier League',
  es: 'La Liga',
  de: 'Bundesliga',
  it: 'Serie A',
  fr: 'Ligue 1',
};
const z = (value, scale, key) => {
  const [mean, sd] = scale[key];
  return sd ? (value - mean) / sd : 0;
};
export const dot = (a, b) => {
  let total = 0;
  for (let i = 0; i < a.length; i++) total += a[i] * b[i];
  return total;
};

export function playerVector(prospect, club, spec) {
  const scale = spec.scale,
    age = Number(prospect.age);
  const position = POSITIONS.includes(prospect.position) ? prospect.position : 'M';
  const number = prospect.number === undefined || prospect.number === null ? null : Number(prospect.number);
  const squad = Math.max(1, club.squad_size || 1);
  const depth = (club.position_counts?.[position] || 0) / squad;
  const pool = spec.nation_pool[prospect.nationality] || 0;
  return [
    1,
    z(age, scale, 'age'),
    ((age - 19) / 3) ** 2,
    position === 'G' ? 1 : 0,
    position === 'D' ? 1 : 0,
    position === 'M' ? 1 : 0,
    position === 'F' ? 1 : 0,
    z(club.level, scale, 'level'),
    z(club.attack, scale, 'attack'),
    z(club.defense, scale, 'defense'),
    number !== null && number >= 1 && number <= 11 ? 1 : 0,
    Math.min(number === null ? 40 : number, 40) / 40,
    depth - POSITION_SHARE[position],
    Math.min(Number(prospect.years_at_club || 0), 5) / 5,
    Math.min(Number(prospect.seasons_seen || 1), 6) / 6,
    z(Number(prospect.debut_age ?? age), scale, 'debut_age'),
    prospect.foreign ? 1 : 0,
    Math.log1p(pool) / 10,
    z(club.youth_rate || 0, scale, 'youth_rate'),
    prospect.status === 'departed' ? 0 : 1,
  ];
}

export function candidateVector(prospect, origin, target, spec, excludeSelf = false) {
  const scale = spec.scale,
    age = Number(prospect.age),
    elite = Number(prospect.elite || 0);
  const position = POSITIONS.includes(prospect.position) ? prospect.position : 'M';
  let squad = Math.max(1, target.squad_size || 1);
  let nationCount = target.nation_counts?.[prospect.nationality] || 0;
  let positionCount = target.position_counts?.[position] || 0;
  if (excludeSelf) {
    squad = Math.max(1, squad - 1);
    nationCount = Math.max(0, nationCount - 1);
    positionCount = Math.max(0, positionCount - 1);
  }
  const levelGap = target.level - origin.level;
  const sameClub = target.club && target.club === origin.club ? 1 : 0;
  const corridor = spec.corridor[(origin.competition || '') + '>' + (target.competition || '')] || 0;
  const youthRate = target.youth_rate || 0;
  const vector = [
    1,
    z(target.level, scale, 'level'),
    z(target.attack, scale, 'attack'),
    z(target.defense, scale, 'defense'),
    z(youthRate, scale, 'youth_rate'),
    target.foreign_share || 0,
    target.turnover || 0,
    Math.log1p(target.u21_count || 0) / 3,
    target.profile_fallback ? 1 : 0,
  ];
  for (const code of COMPETITIONS) vector.push(target.competition === code ? 1 : 0);
  vector.push(
    levelGap,
    levelGap * levelGap,
    (levelGap * Math.max(0, 21 - age)) / 5,
    nationCount / squad,
    Math.max(0, POSITION_SHARE[position] - positionCount / squad) / POSITION_SHARE[position],
    (youthRate * Math.max(0, 21 - age)) / 5,
    corridor,
    sameClub,
    target.competition === origin.competition ? 1 : 0,
    (target.foreign_share || 0) * (prospect.foreign ? 1 : 0),
    // How far a prospect can realistically move depends on how good they are.
    elite * z(target.level, scale, 'level'),
    elite * levelGap,
  );
  return vector;
}

export function softmax(scores) {
  const top = Math.max(...scores);
  const exponent = scores.map(s => Math.exp(s - top));
  const total = exponent.reduce((a, b) => a + b, 0);
  return exponent.map(e => e / total);
}

// Expected outcome class for a prospect first seen at this age, recalibrated
// with the prior offsets fitted on cohorts the weights never saw.
export function progression(prospect, club, model) {
  const vector = playerVector(prospect, club, model.spec);
  const offsets = model.progression.prior_offsets || [];
  const scores = model.progression.weights.map((row, k) => dot(row, vector) + (offsets[k] || 0));
  const probabilities = softmax(scores);
  return {
    vector,
    probabilities,
    outcomes: model.progression.outcomes.map((label, k) => ({ label, probability: probabilities[k] })),
    // Class 0 is censoring, not failure, so the ceiling is read conditionally.
    ceiling:
      probabilities.slice(1).reduce((sum, p, i) => sum + p * (i + 1), 0) /
      Math.max(1e-9, 1 - probabilities[0]),
    observable: 1 - probabilities[0],
  };
}

export function latentPlayer(vector, model) {
  return model.fit.tower.map(row => dot(row, vector));
}

// The ranker is the second stage of a two-stage model: it needs the progression
// model's elite probability for this player. Pass `scored` from withElite() to
// avoid recomputing it per candidate.
function withElite(prospect, origin, model) {
  const result = progression(prospect, origin, model);
  return { ...prospect, elite: result.probabilities[result.probabilities.length - 1] };
}

export function fitScore(prospect, origin, target, model, latent = null, vector = null) {
  const scored = prospect.elite === undefined ? withElite(prospect, origin, model) : prospect;
  const player = vector || playerVector(scored, origin, model.spec);
  const z1 = latent || latentPlayer(player, model);
  const features = candidateVector(scored, origin, target, model.spec);
  const index = target.club_index;
  const style = dot(z1, model.fit.embed[index]);
  const bias = model.fit.club_bias[index];
  return { score: style + bias + dot(model.fit.weights, features), style, bias, features };
}

// Named additive contributions. The latent term is reported as one "style"
// component because its dimensions carry no individual meaning.
export const REASONS = {
  level_gap: 'Step in club level',
  level_gap_sq: 'Size of the level step',
  step_up_young: 'Level step for the age',
  nation_share: 'Compatriots in the squad',
  position_need: 'Gap in that position',
  youth_fit: 'Club plays young players',
  corridor: 'League-to-league transfer corridor',
  same_club: 'Already at this club',
  same_competition: 'Same league',
  foreign_fit: 'Squad used to overseas signings',
  elite_target: 'Projection against club level',
  elite_step: 'Projection against the size of the step',
};

export function explain(result, model) {
  const names = model.candidate_features,
    offset = model.cross_offset,
    parts = [];
  for (let i = offset; i < names.length; i++) {
    const contribution = model.fit.weights[i] * result.features[i];
    if (Math.abs(contribution) > 1e-6)
      parts.push({
        key: names[i],
        label: REASONS[names[i]] || names[i],
        value: result.features[i],
        contribution,
      });
  }
  let club = result.bias;
  for (let i = 0; i < offset; i++) club += model.fit.weights[i] * result.features[i];
  parts.push({
    key: 'club_profile',
    label: 'Club profile and signing record',
    value: null,
    contribution: club,
  });
  parts.push({
    key: 'style',
    label: 'Learned style and corridor match',
    value: null,
    contribution: result.style,
  });
  return parts.sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
}

export function rankClubs(prospect, origin, targets, model, limit = 25) {
  const scored0 = withElite(prospect, origin, model);
  const vector = playerVector(scored0, origin, model.spec);
  const latent = latentPlayer(vector, model);
  const scored = targets.map(target => {
    const result = fitScore(scored0, origin, target, model, latent, vector);
    return { target, score: result.score, result };
  });
  scored.sort((a, b) => b.score - a.score);
  // Softmax over the full candidate set: a share of this shortlist, not a
  // probability that any transfer happens.
  const shares = softmax(scored.map(s => s.score));
  return scored
    .slice(0, limit)
    .map((entry, i) => ({ ...entry, share: shares[i], explanation: explain(entry.result, model) }));
}

export function archetypeOf(latent, model) {
  let best = null,
    bestDistance = Infinity;
  for (const archetype of model.archetypes) {
    let distance = 0;
    for (let i = 0; i < latent.length; i++) distance += (latent[i] - archetype.centre[i]) ** 2;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = archetype;
    }
  }
  return best && { ...best, distance: Math.sqrt(bestDistance) };
}

export function similarTo(latent, pool, limit = 8) {
  const norm = Math.sqrt(dot(latent, latent)) || 1e-9;
  const scored = [];
  for (const entry of pool) {
    const other = entry.latent;
    const length = Math.sqrt(dot(other, other)) || 1e-9;
    scored.push({ entry, similarity: dot(latent, other) / (norm * length) });
  }
  scored.sort((a, b) => b.similarity - a.similarity);
  return scored.slice(0, limit);
}
