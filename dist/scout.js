import {
  playerVector,
  progression,
  rankClubs,
  latentPlayer,
  archetypeOf,
  similarTo,
  fitScore,
  explain,
  POSITION_SHARE,
  POSITION_NAMES,
  COMPETITION_NAMES,
} from './scouting-engine.js';
import { hydrateClubs, hydrateProspects, prospectRecord } from './scout-data.js';
import { $, el, pct } from './dom.js';
import { renderModelCard } from './scout-model-card.js';
const WATCHLIST = 'jogo.scout.v1';

// Everything here runs on data the browser already has; nothing is fetched per
// prospect. The three model files load once, the first time this view opens.
export function createScout({ openInMatchroom, notify }) {
  let model,
    clubs,
    pool,
    mode = 'board',
    selected = null,
    watchOnly = false,
    booted = null;
  const latents = [],
    elite = [],
    observable = [];
  let neighbours = [],
    resolved = [];
  let currentYear = null;
  let refreshWatchButton = () => {};
  // In current scope a prospect's age today is what matters; a past cohort is
  // read at the age they actually were that season.
  const ageFor = prospect =>
    $('scout-year')?.value === 'current' && prospect.age_now != null ? prospect.age_now : prospect.age;
  const text = (id, value) => {
    $(id).textContent = value;
  };

  async function boot() {
    const files = await Promise.all(
      ['model', 'clubs', 'prospects'].map(async name => {
        const response = await fetch(`./scouting/${name}.json`);
        if (!response.ok)
          throw new Error(`Scouting data could not be loaded (${name}.json). Reload to retry.`);
        return response.json();
      }),
    );
    model = files[0];
    clubs = hydrateClubs(files[1]);
    currentYear = files[2].current_year;
    pool = hydrateProspects(files[2], clubs);
    // One pass over the pool: the latent vector and projection every view needs.
    for (const prospect of pool) {
      const club = clubs.byId.get(prospect.edition);
      const vector = playerVector(prospectRecord(prospect), club, model.spec);
      latents.push(latentPlayer(vector, model));
      const projection = progression(prospectRecord(prospect), club, model);
      elite.push(projection.probabilities[projection.probabilities.length - 1]);
      observable.push(projection.observable);
    }
    // Built once: the similarity search reads this on every report.
    neighbours = pool.map((prospect, index) => ({ ...prospect, latent: latents[index] }));
    resolved = neighbours.filter(p => p.outcome !== null && p.outcome !== undefined);
    buildControls();
  }

  function buildControls() {
    const regions = [...new Set(Object.values(model.regions))].sort();
    $('scout-region').append(
      ...regions.map(name =>
        Object.assign(document.createElement('option'), { value: name, textContent: name }),
      ),
    );
    $('scout-competition').append(
      ...Object.entries(COMPETITION_NAMES).map(([code, name]) =>
        Object.assign(document.createElement('option'), { value: code, textContent: name }),
      ),
    );
    const years = [...new Set(pool.map(p => clubs.byId.get(p.edition).year))].sort((a, b) => b - a);
    const seasons = document.createElement('optgroup');
    seasons.label = 'One season';
    seasons.append(
      ...years.map(y =>
        Object.assign(document.createElement('option'), {
          value: String(y),
          textContent: y === currentYear ? `${y} · current` : String(y),
        }),
      ),
    );
    $('scout-year').append(seasons);
    $('cp-nations').append(
      ...Object.keys(model.nations)
        .sort()
        .map(code => Object.assign(document.createElement('option'), { value: code })),
    );
    const current = pool.filter(p => p.current);
    text('scout-current-count', current.length.toLocaleString());
    text('scout-current-season', `${currentYear - 1}/${String(currentYear).slice(2)}`);
    text('scout-nations', String(new Set(current.map(p => p.nationality).filter(Boolean)).size));
    for (const id of [
      'scout-search',
      'scout-position',
      'scout-region',
      'scout-competition',
      'scout-year',
      'scout-age',
      'scout-sort',
    ])
      $(id).addEventListener(id === 'scout-search' ? 'input' : 'change', renderBoard);
    const watch = el('button', 'outline scout-watch-toggle');
    watch.type = 'button';
    watch.onclick = () => {
      watchOnly = !watchOnly;
      watch.classList.toggle('active', watchOnly);
      renderBoard();
    };
    $('scout-search').closest('.scout-filters').append(watch);
    refreshWatchButton = () => {
      watch.textContent = `☆ Watchlist (${readWatchlist().length})`;
      watch.classList.toggle('active', watchOnly);
    };
    refreshWatchButton();
    buildCustomForm();
    buildClubForm();
    renderModelCard(model);
  }

  function readWatchlist() {
    try {
      const rows = JSON.parse(localStorage.getItem(WATCHLIST) || '[]');
      return Array.isArray(rows) ? rows.filter(n => Number.isInteger(n) && n >= 0 && n < pool.length) : [];
    } catch {
      return [];
    }
  }
  function writeWatchlist(rows) {
    try {
      localStorage.setItem(WATCHLIST, JSON.stringify(rows.slice(0, 40)));
      refreshWatchButton();
      return true;
    } catch {
      notify('Browser storage is unavailable, so the watchlist cannot be kept.');
      return false;
    }
  }

  function flag(code) {
    const path = model.flags[code];
    if (!path) return el('span', 'nation-chip', code || '—');
    const image = el('img', 'nation-flag');
    image.src = path;
    image.alt = code;
    image.width = 20;
    image.height = 15;
    image.onerror = () => image.replaceWith(el('span', 'nation-chip', code));
    return image;
  }
  function crest(club, size = 34) {
    if (!club.crest) {
      const initials = el(
        'span',
        'fallback-crest scout-crest',
        club.name
          .split(/\s+/)
          .map(w => w[0])
          .slice(0, 3)
          .join(''),
      );
      return initials;
    }
    const image = el('img', 'scout-crest');
    image.src = club.crest;
    image.alt = '';
    image.width = size;
    image.height = Math.round(size * 1.12);
    image.onerror = () =>
      image.replaceWith(
        el(
          'span',
          'fallback-crest scout-crest',
          club.name
            .split(/\s+/)
            .map(w => w[0])
            .slice(0, 3)
            .join(''),
        ),
      );
    return image;
  }

  // ---- Prospect board
  function filtered() {
    const query = $('scout-search').value.trim().toLocaleLowerCase();
    const position = $('scout-position').value,
      region = $('scout-region').value;
    const competition = $('scout-competition').value,
      scope = $('scout-year').value;
    const maxAge = Number($('scout-age').value),
      watch = new Set(watchOnly ? readWatchlist() : []);
    const rows = [];
    for (const prospect of pool) {
      if (watchOnly && !watch.has(prospect.index)) continue;
      if (ageFor(prospect) > maxAge) continue;
      if (position !== 'all' && prospect.position !== position) continue;
      if (region !== 'all' && model.regions[prospect.nationality] !== region) continue;
      const club = clubs.byId.get(prospect.edition);
      if (competition !== 'all' && club.competition !== competition) continue;
      if (scope === 'current' && !prospect.current) continue;
      if (scope === 'tracked' && prospect.outcome === null) continue;
      if (/^\d{4}$/.test(scope) && String(club.year) !== scope) continue;
      if (
        query &&
        !`${prospect.name} ${club.name} ${prospect.nationality || ''}`.toLocaleLowerCase().includes(query)
      )
        continue;
      rows.push(prospect);
    }
    const sort = $('scout-sort').value;
    const compare = {
      elite: (a, b) => elite[b.index] - elite[a.index],
      observable: (a, b) => observable[b.index] - observable[a.index],
      age: (a, b) => ageFor(a) - ageFor(b) || elite[b.index] - elite[a.index],
      name: (a, b) => a.name.localeCompare(b.name),
    }[sort];
    rows.sort(compare);
    return rows;
  }

  function renderBoard() {
    const rows = filtered(),
      root = $('scout-list');
    const scope = $('scout-year').value;
    const scopeLabel =
      scope === 'current'
        ? `in the ${currentYear - 1}/${String(currentYear).slice(2)} squads, aged as of today`
        : scope === 'tracked'
          ? 'from past cohorts whose outcome is recorded'
          : scope === 'all'
            ? 'across every season in the snapshot'
            : `from the ${scope} season`;
    text(
      'scout-pool-count',
      `${rows.length.toLocaleString()} players ${scopeLabel} · ${new Set(rows.map(r => r.nationality).filter(Boolean)).size} nationalities`,
    );
    root.replaceChildren();
    if (!rows.length) {
      root.append(el('p', 'empty-state', 'No prospect matches these filters.'));
      return;
    }
    for (const prospect of rows.slice(0, 150)) {
      const club = clubs.byId.get(prospect.edition);
      const card = el(
        'button',
        'scout-card' + (selected && selected.index === prospect.index ? ' active' : ''),
      );
      card.type = 'button';
      card.setAttribute('role', 'listitem');
      const head = el('div', 'scout-card-head');
      const shown = ageFor(prospect);
      const age = el('span', 'scout-age', `${shown}`);
      age.title =
        prospect.age_now != null && prospect.age_now !== prospect.age
          ? `${prospect.age_now} today · ${prospect.age} during ${club.year - 1}/${String(club.year).slice(2)}`
          : `${prospect.age} during ${club.year - 1}/${String(club.year).slice(2)}`;
      head.append(flag(prospect.nationality), el('strong', '', prospect.name), age);
      const meta = el('div', 'scout-card-meta');
      meta.append(
        el('span', '', `${POSITION_NAMES[prospect.position]} · ${club.name}`),
        el('span', '', club.year),
      );
      const track = el('div', 'scout-card-track');
      const bar = el('b');
      bar.style.width = (elite[prospect.index] * 100).toFixed(1) + '%';
      track.append(bar);
      card.append(
        head,
        meta,
        track,
        el('small', 'scout-card-score', `${pct(elite[prospect.index])} elite-club projection`),
      );
      card.onclick = () => {
        selected = prospect;
        renderBoard();
        renderReport(prospect, $('scout-report'));
      };
      root.append(card);
    }
    if (rows.length > 150)
      root.append(
        el(
          'p',
          'lab-footnote',
          `First 150 of ${rows.length.toLocaleString()}. Narrow the filters to see further.`,
        ),
      );
  }

  // ---- Fit ranking, shared by the board and the custom form
  function fitFor(record, origin, scope, limit = 12) {
    // The newest season in the snapshot has no following season, so the latest
    // squads are ranked against their own season and the copy says so.
    const nextYear = clubs.byYear.has(origin.year + 1) ? origin.year + 1 : origin.year;
    const targets = (scope === 'next' ? clubs.byYear.get(nextYear) || [] : clubs.list).filter(
      club => club.club !== origin.club,
    );
    if (!targets.length)
      return { entries: [], targets, year: nextYear, sameSeason: nextYear === origin.year };
    const ranked = rankClubs(record, origin, targets, model, targets.length);
    const best = new Map();
    for (const entry of ranked) if (!best.has(entry.target.club)) best.set(entry.target.club, entry);
    const grouped = [...best.values()];
    const total = grouped.reduce((sum, entry) => sum + entry.share, 0) || 1;
    return {
      entries: grouped.slice(0, limit).map(entry => ({ ...entry, share: entry.share / total })),
      targets,
      clubs: grouped.length,
      year: nextYear,
      sameSeason: nextYear === origin.year,
    };
  }

  function reasonList(entry) {
    const list = el('div', 'fit-reasons');
    for (const part of entry.explanation.slice(0, 4)) {
      const chip = el('span', 'fit-reason' + (part.contribution > 0 ? ' positive' : ' negative'));
      chip.append(
        el('b', '', part.label),
        el('i', '', (part.contribution > 0 ? '+' : '') + part.contribution.toFixed(2)),
      );
      chip.title =
        part.value === null
          ? `${part.label}: ${part.contribution.toFixed(3)} added to the fit score`
          : `${part.label}: feature ${part.value.toFixed(3)} × weight = ${part.contribution.toFixed(3)}`;
      list.append(chip);
    }
    return list;
  }

  function renderReport(prospect, root, options = {}) {
    const club = options.overrideClub || clubs.byId.get(prospect.edition);
    const record = options.record || prospectRecord(prospect);
    const scope = options.scope || 'next';
    const vector = playerVector(record, club, model.spec);
    const latent = latentPlayer(vector, model);
    const projection = progression(record, club, model);
    const archetype = archetypeOf(latent, model);
    root.replaceChildren();

    const header = el('div', 'scout-report-head');
    const identity = el('div', 'scout-identity');
    identity.append(flag(prospect.nationality), el('h3', '', prospect.name || 'Unnamed prospect'));
    const line = el('p', 'scout-identity-meta');
    const season = `${club.year - 1}/${String(club.year).slice(2)}`;
    const ageText =
      prospect.age_now != null && prospect.age_now !== prospect.age
        ? `${prospect.age_now} today · ${prospect.age} in ${season}`
        : `${prospect.age} years`;
    line.textContent = `${ageText} · ${POSITION_NAMES[prospect.position]}${prospect.number ? ` · number ${prospect.number}` : ''} · ${prospect.nationality || 'nationality unknown'}`;
    identity.append(line);
    const current = el('div', 'scout-current-club');
    current.append(crest(club, 40));
    const where = el('div');
    where.append(
      el('strong', '', club.name),
      el('span', '', `${club.competition_name || COMPETITION_NAMES[club.competition]} ${club.year}`),
    );
    current.append(where);
    header.append(identity, current);
    root.append(header);
    if (archetype)
      root.append(el('p', 'scout-archetype', `Closest archetype in the learned space: ${archetype.label}.`));

    // Projection
    const projectionPanel = el('div', 'scout-block');
    projectionPanel.append(el('h4', '', 'Where they are listed next'));
    projectionPanel.append(
      el(
        'p',
        'scout-block-note',
        `Which calibre of squad list a player first seen at this age and level appears on, from ${model.progression.metrics.settle + 1} to ${model.progression.metrics.horizon} seasons later. A squad list records who a club registered, not who played, so this is where a career is listed — not how good it became.`,
      ),
    );
    const bars = el('div', 'outcome-bars');
    projection.outcomes.forEach((outcome, index) => {
      const row = el('div', 'outcome-row');
      row.dataset.outcome = String(index);
      const track = el('span', 'outcome-track');
      const fill = el('b');
      fill.style.width = (outcome.probability * 100).toFixed(1) + '%';
      track.append(fill);
      row.append(
        el('span', 'outcome-label', outcome.label),
        track,
        el('strong', '', pct(outcome.probability)),
      );
      bars.append(row);
    });
    projectionPanel.append(bars);
    projectionPanel.append(
      el(
        'p',
        'lab-footnote',
        `“No further top-five squad” is censoring, not failure: a move to a league outside these five looks the same in this data. Being at a strong club already is the single biggest driver here, so the highest projections sit on big-club academy intakes almost by construction. Held-out accuracy ${pct(model.progression.metrics.accuracy)} against ${pct(model.progression.metrics.majority_accuracy)} for always predicting the most common outcome.`,
      ),
    );
    if (prospect.outcome !== null && prospect.outcome !== undefined) {
      const truth = el('p', 'scout-truth');
      const peak = prospect.peak_edition ? clubs.byId.get(prospect.peak_edition) : null;
      truth.append(
        el('b', '', 'WHAT THE SNAPSHOT RECORDS: '),
        document.createTextNode(
          `${model.progression.outcomes[prospect.outcome]}${peak ? ` · peak squad ${peak.name} ${peak.year}` : ''}`,
        ),
      );
      projectionPanel.append(truth);
    } else if (!options.custom) {
      projectionPanel.append(
        el(
          'p',
          'scout-truth',
          `This player's six-season window runs past the ${model.as_of} cutoff, so no outcome is recorded yet.`,
        ),
      );
    }
    root.append(projectionPanel);

    // Club fit
    const fit = fitFor(record, club, scope);
    const fitPanel = el('div', 'scout-block');
    fitPanel.append(el('h4', '', 'Where players like this go next'));
    fitPanel.append(
      el(
        'p',
        'scout-block-note',
        scope !== 'next'
          ? `Closest-matching edition of each of ${fit.clubs || 0} club identities, every era considered.`
          : fit.sameSeason
            ? `Ranked across the ${fit.targets.length} other clubs of ${fit.year}, the newest season in this snapshot. There is no later season to rank against yet.`
            : `Ranked across the ${fit.targets.length} club editions of ${fit.year}, excluding their current club.`,
      ),
    );
    fitPanel.append(
      el(
        'p',
        'scout-block-note',
        'This ranks the destinations players with this profile were actually recorded moving to. The source cannot separate a loan from a transfer, so for a teenager at a strong club the likeliest next club is often a smaller one — the model is reporting the market, not naming who ought to sign them.',
      ),
    );
    for (const entry of fit.entries) {
      const row = el('article', 'fit-row');
      row.append(crest(entry.target, 30));
      const body = el('div', 'fit-body');
      const head = el('div', 'fit-head');
      head.append(
        el('strong', '', entry.target.name),
        el('span', '', `${COMPETITION_NAMES[entry.target.competition]} ${entry.target.year}`),
      );
      body.append(head, reasonList(entry));
      const share = el('div', 'fit-share');
      share.append(el('strong', '', pct(entry.share)), el('small', '', 'fit share'));
      const open = el('button', 'outline', 'Matchroom ↗');
      open.onclick = () => openInMatchroom(entry.target.id);
      open.title = `Load ${entry.target.name} ${entry.target.year} as the home side`;
      row.append(body, share, open);
      fitPanel.append(row);
    }
    if (!fit.entries.length)
      fitPanel.append(el('p', 'empty-state', 'No destination season is available for this edition.'));
    fitPanel.append(
      el(
        'p',
        'lab-footnote',
        `Fit is learned from ${model.fit.metrics.train_moves.toLocaleString()} real club-to-club moves, so it reflects the recruitment market rather than merit. On held-out later seasons the true destination lands in the top five of about ${fit.targets.length} candidates ${pct(model.fit.metrics.model.recall_5)} of the time, against ${pct(model.fit.metrics.closest_level.recall_5)} for ranking by closest club level. Shares are a split of this shortlist, not a probability that any transfer happens.`,
      ),
    );
    root.append(fitPanel);

    // Comparable prospects
    if (!options.custom || options.compare !== false) {
      // For a player whose own outcome is still unknown, the useful comparison is
      // to past players who look the same and whose careers are already recorded.
      const tracked = prospect.outcome === null || prospect.outcome === undefined;
      const field = tracked ? resolved : neighbours;
      const matches = similarTo(latent, field, options.custom ? 9 : 10)
        .filter(match => options.custom || match.entry.index !== prospect.index)
        .slice(0, 6);
      const comparePanel = el('div', 'scout-block');
      comparePanel.append(
        el('h4', '', tracked ? 'Players who looked like this, and what happened' : 'Profiles like this'),
      );
      comparePanel.append(
        el(
          'p',
          'scout-block-note',
          tracked
            ? 'Nearest past prospects by cosine similarity in the ranker’s learned player space, restricted to careers the snapshot can already score. A shared profile is not a shared ability, and six neighbours are an illustration, not a forecast.'
            : 'Nearest prospects by cosine similarity in the ranker’s learned player space. A shared profile is not a shared ability.',
        ),
      );
      const list = el('div', 'compare-list');
      for (const match of matches) {
        const other = match.entry,
          otherClub = clubs.byId.get(other.edition);
        const card = el('button', 'compare-card');
        card.type = 'button';
        card.append(
          flag(other.nationality),
          el('strong', '', other.name),
          el('span', '', `${otherClub.name} ${otherClub.year} · ${other.age}`),
          el(
            'small',
            '',
            `${(match.similarity * 100).toFixed(1)}% profile match${other.outcome !== null && other.outcome !== undefined ? ` · ${model.progression.outcomes[other.outcome].toLowerCase()}` : ''}`,
          ),
        );
        card.onclick = () => {
          selected = other;
          setMode('board');
          renderBoard();
          renderReport(other, $('scout-report'));
          $('scout-report').scrollIntoView({ block: 'start', behavior: 'smooth' });
        };
        list.append(card);
      }
      comparePanel.append(list);
      root.append(comparePanel);
    }

    // Actions
    const actions = el('div', 'scout-actions');
    if (!options.custom) {
      const watchlist = readWatchlist();
      const saved = watchlist.includes(prospect.index);
      const save = el('button', 'outline', saved ? '★ On your watchlist' : '☆ Add to watchlist');
      save.onclick = () => {
        const rows = readWatchlist();
        const next = rows.includes(prospect.index)
          ? rows.filter(i => i !== prospect.index)
          : [prospect.index, ...rows];
        if (writeWatchlist(next)) {
          notify(
            rows.includes(prospect.index)
              ? 'Removed from your watchlist.'
              : 'Added to your watchlist, in this browser only.',
          );
          renderReport(prospect, root, options);
          renderBoard();
        }
      };
      actions.append(save);
    }
    const home = el('button', 'outline', 'Open their club in the Matchroom ↗');
    home.onclick = () => openInMatchroom(club.id);
    actions.append(home);
    root.append(actions);
    root.append(
      el(
        'p',
        'source-credit',
        `Squad snapshot: FootballSquads. Club profile for ${club.name} ${club.year} describes the squad and results of ${club.profile_source}${club.profile_fallback ? ' (no earlier season available, so its own season is used)' : ''}.`,
      ),
    );
  }

  // ---- Custom prospect
  function buildCustomForm() {
    const search = $('cp-club-search'),
      select = $('cp-club');
    function populate() {
      const query = search.value.trim().toLocaleLowerCase();
      const matches = clubs.list
        .filter(club => !query || `${club.name} ${club.year}`.toLocaleLowerCase().includes(query))
        .sort((a, b) => a.name.localeCompare(b.name) || b.year - a.year)
        .slice(0, 60);
      select.replaceChildren(
        ...matches.map(club =>
          Object.assign(document.createElement('option'), {
            value: club.id,
            textContent: `${club.name} ${club.year} · ${COMPETITION_NAMES[club.competition]}`,
          }),
        ),
      );
      if (!matches.length)
        select.append(
          Object.assign(document.createElement('option'), {
            value: '',
            textContent: 'No club edition matches',
          }),
        );
    }
    search.oninput = populate;
    const mode = $('cp-level');
    const sync = () => {
      $('cp-club-wrap').hidden = mode.value !== 'club';
      $('cp-band-wrap').hidden = mode.value !== 'band';
    };
    mode.onchange = sync;
    sync();
    populate();
    $('cp-run').onclick = runCustom;
  }

  // A band is a stand-in for a real club: the median club edition at that
  // strength quartile, which is an assumption and is labelled as one.
  function bandProfile(band) {
    const sorted = [...clubs.list].sort((a, b) => a.level - b.level);
    const share = [0.15, 0.4, 0.65, 0.9][Math.min(3, Math.max(0, Number(band) - 1))];
    const club = sorted[Math.floor(share * (sorted.length - 1))];
    return {
      ...club,
      name: `${['Lower-table', 'Mid-table', 'Continental-level', 'Elite'][Number(band) - 1]} reference club`,
      id: club.id,
      crest: null,
    };
  }

  function runCustom() {
    const error = message => {
      text('cp-error', message);
      $('cp-error').hidden = false;
    };
    try {
      const age = Number($('cp-age').value);
      if (!Number.isFinite(age) || age < 14 || age > 23) throw new Error('Enter an age between 14 and 23.');
      const nationality = $('cp-nationality').value.trim().toUpperCase();
      if (nationality && !/^[A-Z]{3}$/.test(nationality))
        throw new Error('Use a three-letter nationality code, or leave it blank.');
      const numberValue = $('cp-number').value.trim();
      const club =
        $('cp-level').value === 'club' ? clubs.byId.get($('cp-club').value) : bandProfile($('cp-band').value);
      if (!club) throw new Error('Choose a club edition to use as the current level.');
      const record = {
        name: $('cp-name').value.trim() || 'Your prospect',
        age,
        position: $('cp-position').value,
        nationality: nationality || null,
        number: numberValue === '' ? null : Number(numberValue),
        years_at_club: Number($('cp-years').value || 0),
        seasons_seen: Number($('cp-seasons').value || 1),
        debut_age: age - Math.max(0, Number($('cp-seasons').value || 1) - 1),
        foreign:
          nationality && model.regions[nationality]
            ? club.competition && !homeCodes(club.competition).includes(nationality)
              ? 1
              : 0
            : 1,
        status: 'listed',
      };
      $('cp-error').hidden = true;
      const display = {
        ...record,
        index: -1,
        edition: club.id,
        nationality: record.nationality,
        outcome: null,
        peak_edition: null,
        departed: 0,
        identity: -1,
      };
      renderReport(display, $('scout-custom-report'), {
        record,
        custom: true,
        scope: $('cp-era').value,
        overrideClub: club,
      });
      if (!model.nations[record.nationality] && record.nationality)
        notify(
          `${record.nationality} does not appear in the bundled squads, so the nationality features fall back to an empty pool.`,
        );
    } catch (e) {
      error(e.message);
    }
  }
  const homeCodes = competition =>
    ({ en: ['ENG', 'WAL', 'SCO', 'NIR'], es: ['ESP'], de: ['GER'], it: ['ITA'], fr: ['FRA'] })[competition] ||
    [];

  // ---- Model card

  // ---- Recruit for a club: the same ranker, held fixed at one destination.
  function buildClubForm() {
    const search = $('cn-search'),
      select = $('cn-club');
    function populate() {
      const query = search.value.trim().toLocaleLowerCase();
      const matches = clubs.list
        .filter(club => !query || club.name.toLocaleLowerCase().includes(query))
        .sort((a, b) => b.year - a.year || a.name.localeCompare(b.name))
        .slice(0, 80);
      select.replaceChildren(
        ...matches.map(club =>
          Object.assign(document.createElement('option'), {
            value: club.id,
            textContent: `${club.name} ${club.year} · ${COMPETITION_NAMES[club.competition]}`,
          }),
        ),
      );
      if (!matches.length)
        select.append(
          Object.assign(document.createElement('option'), { value: '', textContent: 'No club matches' }),
        );
    }
    search.oninput = () => {
      populate();
      renderClubNeeds();
    };
    populate();
    // Open on a current-season club so the default view is a live squad.
    const current = clubs.list.find(c => c.year === currentYear);
    if (current) select.value = current.id;
    for (const id of ['cn-club', 'cn-position', 'cn-scope', 'cn-age', 'cn-sort'])
      $(id).addEventListener('change', renderClubNeeds);
  }

  // Positions carrying fewer than their share of an eleven, worst first.
  function squadNeeds(club) {
    const squad = Math.max(1, club.squad_size || 1);
    return Object.keys(POSITION_SHARE)
      .map(group => ({
        group,
        share: (club.position_counts[group] || 0) / squad,
        deficit: POSITION_SHARE[group] - (club.position_counts[group] || 0) / squad,
      }))
      .sort((a, b) => b.deficit - a.deficit);
  }

  function renderClubNeeds() {
    if (!model) return;
    const club = clubs.byId.get($('cn-club').value);
    const root = $('cn-report'),
      panel = $('cn-squad');
    panel.replaceChildren();
    root.replaceChildren();
    if (!club) {
      root.append(el('p', 'empty-state', 'Choose a club edition.'));
      return;
    }

    const needs = squadNeeds(club);
    const summary = el('div', 'club-summary');
    for (const [label, value] of [
      ['Squad listed', String(club.squad_size)],
      ['Mean age', club.mean_age ? club.mean_age.toFixed(1) : '—'],
      ['Under-21 share', pct(club.youth_rate)],
      ['Overseas share', pct(club.foreign_share)],
    ]) {
      const cell = el('div');
      cell.append(el('span', '', label), el('strong', '', value));
      summary.append(cell);
    }
    panel.append(summary);
    const shape = el('div', 'club-shape');
    for (const need of Object.keys(POSITION_SHARE).map(g => needs.find(n => n.group === g))) {
      const row = el('div', 'club-shape-row');
      const track = el('span', 'outcome-track');
      const fill = el('b');
      fill.style.width = Math.min(100, (need.share / POSITION_SHARE[need.group]) * 50).toFixed(1) + '%';
      track.append(fill);
      row.append(
        el('span', 'outcome-label', POSITION_NAMES[need.group]),
        track,
        el('strong', '', (club.position_counts[need.group] || 0) + (need.deficit > 0.02 ? ' · thin' : '')),
      );
      shape.append(row);
    }
    panel.append(shape);
    panel.append(
      el(
        'p',
        'lab-footnote',
        `Squad shape describes ${club.profile_source}, the season before this one, which is what the ranker sees. ` +
          `A bar at the halfway mark is the share of an eleven that position would normally take.`,
      ),
    );

    // Rank the pool at this fixed destination.
    const wanted = $('cn-position').value;
    const groups =
      wanted === 'need'
        ? needs
            .filter(n => n.deficit > 0)
            .slice(0, 2)
            .map(n => n.group)
        : null;
    const scope = $('cn-scope').value,
      maxAge = Number($('cn-age').value),
      sort = $('cn-sort').value;
    const rows = [];
    for (const prospect of pool) {
      if (scope === 'current' && !prospect.current) continue;
      if ((prospect.age_now ?? prospect.age) > maxAge) continue;
      if (groups && !groups.includes(prospect.position)) continue;
      if (wanted !== 'need' && wanted !== 'all' && prospect.position !== wanted) continue;
      const origin = clubs.byId.get(prospect.edition);
      if (origin.club === club.club) continue; // already there
      const record = prospectRecord(prospect);
      const result = fitScore(record, origin, club, model, latents[prospect.index]);
      rows.push({ prospect, origin, score: result.score, result });
    }
    rows.sort(
      sort === 'elite'
        ? (a, b) => elite[b.prospect.index] - elite[a.prospect.index] || b.score - a.score
        : (a, b) => b.score - a.score,
    );

    const head = el('div', 'scout-report-head');
    const identity = el('div', 'scout-identity');
    identity.append(el('h3', '', club.name));
    identity.append(
      el(
        'p',
        'scout-identity-meta',
        `${COMPETITION_NAMES[club.competition]} ${club.year} · ranking ${rows.length.toLocaleString()} prospects` +
          (groups ? ` · thinnest: ${groups.map(g => POSITION_NAMES[g].toLowerCase()).join(' and ')}` : ''),
      ),
    );
    head.append(identity);
    const image = crest(club, 40);
    head.append(image);
    root.append(head);

    if (!rows.length) {
      root.append(el('p', 'empty-state', 'No prospect matches these filters.'));
      return;
    }
    const list = el('div', 'scout-block');
    list.append(el('h4', '', 'Prospects the ranker places here'));
    list.append(
      el(
        'p',
        'scout-block-note',
        'Scored with the same model the player view uses, held fixed at this destination. Reasons show only the ' +
          'terms that differ across this shortlist, since the rest describe the club and are identical for everyone ' +
          'on it. The ranker is trained on where players were actually recorded moving, so this reads the ' +
          'recruitment market for a club of this profile, not a judgement that the club should sign them.',
      ),
    );
    const shortlist = rows.slice(0, 15).map(row => ({ ...row, parts: explain(row.result, model) }));
    // Held at one destination, most terms are identical for everyone on the list:
    // they explain the club, not the player. Show only what separates them.
    const spread = new Map();
    for (const row of shortlist)
      for (const part of row.parts) {
        const seen = spread.get(part.key) || new Set();
        seen.add(part.contribution.toFixed(4));
        spread.set(part.key, seen);
      }
    const varying = new Set([...spread].filter(([, values]) => values.size > 1).map(([key]) => key));
    for (const row of shortlist) {
      const article = el('article', 'fit-row');
      article.append(flag(row.prospect.nationality));
      const body = el('div', 'fit-body');
      const title = el('div', 'fit-head');
      title.append(
        el('strong', '', row.prospect.name),
        el(
          'span',
          '',
          `${POSITION_NAMES[row.prospect.position]} · ${row.origin.name} ${row.origin.year} · ` +
            `${row.prospect.age_now ?? row.prospect.age}`,
        ),
      );
      body.append(title);
      const reasons = el('div', 'fit-reasons');
      const distinct = row.parts.filter(part => varying.has(part.key));
      for (const part of (distinct.length ? distinct : row.parts).slice(0, 3)) {
        const chip = el('span', 'fit-reason' + (part.contribution > 0 ? ' positive' : ' negative'));
        chip.append(
          el('b', '', part.label),
          el('i', '', (part.contribution > 0 ? '+' : '') + part.contribution.toFixed(2)),
        );
        reasons.append(chip);
      }
      body.append(reasons);
      const score = el('div', 'fit-share');
      score.append(el('strong', '', pct(elite[row.prospect.index])), el('small', '', 'elite projection'));
      const open = el('button', 'outline', 'Report ↗');
      open.onclick = () => {
        selected = row.prospect;
        setMode('board');
        renderBoard();
        renderReport(row.prospect, $('scout-report'));
        $('scout-report').scrollIntoView({ block: 'start' });
      };
      article.append(body, score, open);
      list.append(article);
    }
    root.append(list);
    root.append(
      el(
        'p',
        'lab-footnote',
        `Showing the top 15 of ${rows.length.toLocaleString()}. Prospects already at this club are left out. ` +
          `Elite projection is the progression model's own output and does not depend on the club chosen here.`,
      ),
    );
  }

  function setMode(next) {
    mode = next;
    for (const button of document.querySelectorAll('.scout-mode')) {
      const active = button.dataset.mode === next;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    }
    $('scout-board').hidden = next !== 'board';
    $('scout-custom').hidden = next !== 'custom';
    $('scout-club').hidden = next !== 'club';
    $('scout-model').hidden = next !== 'model';
    if (next === 'club') renderClubNeeds();
  }

  async function show() {
    if (!booted) {
      booted = boot().catch(e => {
        booted = null;
        throw e;
      });
      try {
        await booted;
      } catch (e) {
        $('scout-loading').textContent = e.message;
        return;
      }
      $('scout-loading').hidden = true;
      for (const button of document.querySelectorAll('.scout-mode'))
        button.onclick = () => setMode(button.dataset.mode);
      setMode('board');
      renderBoard();
      return;
    }
    await booted;
    setMode(mode);
  }
  return { show };
}
