import { REASONS } from './scouting-engine.js';
import { $, el, pct } from './dom.js';

// The Scout lab's model card: held-out numbers, the baselines they are measured
// against, and the declared limits. Reads only the exported model file.
export function renderModelCard(model) {
  const root = $('scout-model');
  root.replaceChildren();
  const fit = model.fit.metrics,
    prog = model.progression.metrics;
  const intro = el('section', 'panel');
  intro.append(el('h3', '', 'How these models were fitted'));
  intro.append(el('p', 'scout-block-note', model.method));
  const facts = el('div', 'model-facts');
  for (const [label, value] of [
    ['Prospect pool', `${model.pool.size.toLocaleString()} under-${model.pool.max_age} club seasons`],
    ['Distinct players', model.pool.identities.toLocaleString()],
    ['Outcomes observable', `${model.pool.labelled.toLocaleString()} of ${model.pool.size.toLocaleString()}`],
    ['Moves used for fit', fit.train_moves.toLocaleString()],
    ['Latent dimensions', fit.latent],
    ['Snapshot cutoff', model.as_of],
  ]) {
    const cell = el('div');
    cell.append(el('span', '', label), el('strong', '', String(value)));
    facts.append(cell);
  }
  intro.append(facts);
  root.append(intro);

  const fitPanel = el('section', 'panel');
  fitPanel.append(el('h3', '', 'Club fit: ranking the true destination'));
  fitPanel.append(
    el(
      'p',
      'scout-block-note',
      `Validation uses every observed move from ${fit.validation_from} onwards, seasons the weights never saw. Each move is ranked against the roughly ${fit.candidates_mean} club editions available that season. Baselines face the identical task.`,
    ),
  );
  const table = el('table'),
    head = el('thead'),
    headRow = el('tr');
  for (const label of ['', 'TOP 1', 'TOP 5', 'TOP 10', 'TOP 25', 'MRR', 'MEDIAN RANK'])
    headRow.append(el('th', '', label));
  head.append(headRow);
  table.append(head);
  const body = el('tbody');
  for (const [label, metrics] of [
    ['This model', fit.model],
    ['Most-active clubs', fit.popularity],
    ['Closest club level', fit.closest_level],
  ]) {
    const row = el('tr');
    if (label === 'This model') row.className = 'model-row';
    row.append(el('td', '', label));
    for (const value of [metrics.recall_1, metrics.recall_5, metrics.recall_10, metrics.recall_25])
      row.append(el('td', '', pct(value)));
    row.append(el('td', '', metrics.mrr.toFixed(3)), el('td', '', String(metrics.median_rank)));
    body.append(row);
  }
  table.append(body);
  const wrap = el('div', 'table-wrap');
  wrap.append(table);
  fitPanel.append(wrap);
  fitPanel.append(
    el(
      'p',
      'lab-footnote',
      `n = ${fit.model.n.toLocaleString()} held-out moves. Trained on one true destination against ${fit.negatives} sampled alternatives. The model has no fitted view on a player staying put: it only ever saw moves, so the "already at this club" term keeps a zero weight.`,
    ),
  );
  root.append(fitPanel);

  const learned = el('section', 'panel');
  learned.append(el('h3', '', 'What the ranker learned'));
  learned.append(
    el(
      'p',
      'scout-block-note',
      'Fitted weights on the named player x club terms, largest first. These are the whole of the explainable part of a fit score; the rest is the latent style term and the club profile.',
    ),
  );
  const weightTable = el('table'),
    weightHead = el('thead'),
    weightRow = el('tr');
  for (const label of ['TERM', 'WEIGHT', 'READS AS']) weightRow.append(el('th', '', label));
  weightHead.append(weightRow);
  weightTable.append(weightHead);
  const weightBody = el('tbody');
  const terms = model.candidate_features
    .slice(model.cross_offset)
    .map((key, index) => ({ key, weight: model.fit.weights[model.cross_offset + index] }))
    .sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight));
  for (const term of terms) {
    const row = el('tr');
    row.append(
      el('td', '', REASONS[term.key] || term.key),
      el('td', '', term.weight.toFixed(3)),
      el(
        'td',
        '',
        term.weight === 0
          ? 'never varied in training'
          : term.weight > 0
            ? 'raises the fit score'
            : 'lowers the fit score',
      ),
    );
    weightBody.append(row);
  }
  weightTable.append(weightBody);
  const weightWrap = el('div', 'table-wrap');
  weightWrap.append(weightTable);
  learned.append(weightWrap);
  learned.append(
    el(
      'p',
      'lab-footnote',
      'A gap at the prospect’s position and compatriots already in the squad dominate, which says as much about how recruitment works as about the players. The level terms are negative and the young-step-up term positive: large jumps are rare, and rarer still except for the youngest players.',
    ),
  );
  root.append(learned);

  const progPanel = el('section', 'panel');
  progPanel.append(el('h3', '', 'Progression: the six-season outcome'));
  progPanel.append(
    el(
      'p',
      'scout-block-note',
      `Cohorts up to ${prog.validation_from - 3} fit the weights, ${prog.validation_from - 2}–${prog.validation_from - 1} fit the class priors, and ${prog.validation_from} onwards is held out. Tier boundaries come from the training split only.`,
    ),
  );
  const metrics = el('div', 'model-facts');
  for (const [label, value] of [
    ['Accuracy', `${pct(prog.accuracy)} vs ${pct(prog.majority_accuracy)} majority`],
    ['Brier score', `${prog.brier} vs ${prog.base_rate_brier} base rate`],
    ['Before recalibration', String(prog.uncalibrated_brier)],
    ['Training cohorts', prog.train.toLocaleString()],
    ['Held-out cohorts', prog.validation.toLocaleString()],
  ]) {
    const cell = el('div');
    cell.append(el('span', '', label), el('strong', '', String(value)));
    metrics.append(cell);
  }
  progPanel.append(metrics);
  const calibration = el('table'),
    calibrationHead = el('thead'),
    calibrationRow = el('tr');
  for (const label of ['OUTCOME', 'AUC', 'PREDICTED', 'OBSERVED']) calibrationRow.append(el('th', '', label));
  calibrationHead.append(calibrationRow);
  calibration.append(calibrationHead);
  const calibrationBody = el('tbody');
  for (const row of prog.calibration) {
    const tr = el('tr');
    tr.append(
      el('td', '', row.outcome),
      el('td', '', prog.auc[row.outcome].toFixed(3)),
      el('td', '', pct(row.predicted)),
      el('td', '', pct(row.observed)),
    );
    calibrationBody.append(tr);
  }
  calibration.append(calibrationBody);
  const calibrationWrap = el('div', 'table-wrap');
  calibrationWrap.append(calibration);
  progPanel.append(calibrationWrap);
  progPanel.append(
    el(
      'p',
      'lab-footnote',
      'AUC near 0.5 means that class is barely separable; the middle tiers are the hard ones and the table says so. Predicted and observed columns are the held-out cohorts.',
    ),
  );
  root.append(progPanel);

  const limits = el('section', 'panel');
  limits.append(el('h3', '', 'What this cannot tell you'));
  const list = el('ul', 'scout-limits');
  for (const limit of model.limits) list.append(el('li', '', limit));
  for (const limit of [
    'There is no academy data here. The pool is the under-21 players in the bundled senior-squad snapshots, which is the youngest cohort this repository can observe, not a youth-team intake.',
    'A hand-entered prospect is scored from the attributes you supply. The model has no way to verify them.',
    'Positions come from the source listing, and no minutes, fees or valuations exist in this data at all.',
    `Archetypes are k-means clusters over the fit model's latent space, named from their members' own averages.`,
  ])
    list.append(el('li', '', limit));
  limits.append(list);
  limits.append(
    el(
      'p',
      'source-credit',
      `Models rebuilt by scripts/build_scouting.py with seed ${model.seed}. Source: ${model.source}.`,
    ),
  );
  root.append(limits);
}
