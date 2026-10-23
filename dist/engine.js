// Pure replay calculations, shared by every dashboard view.
export function snapshot(match, minute) {
  const events = match.events.filter(e => e.minute <= minute);
  const stats = Object.fromEntries(
    ['home', 'away'].map(team => [team, { goals: 0, xg: 0, shots: 0, target: 0, passes: 0, complete: 0 }]),
  );
  for (const e of events) {
    const s = stats[e.team];
    if (e.type === 'shot') {
      s.shots++;
      s.xg += e.xg;
      if (e.outcome === 'goal') s.goals++;
      if (['goal', 'saved'].includes(e.outcome)) s.target++;
    } else if (e.type === 'pass') {
      s.passes++;
      if (e.outcome === 'complete') s.complete++;
    }
  }
  return { events, stats };
}
export function probabilities(stats, minute, rates = null) {
  const remaining = Math.max(0, (90 - minute) / 90);
  const rate = team => remaining * (rates ? rates[team] : 1.35 + 0.35 * stats[team].xg);
  const poisson = lambda => {
    const a = [Math.exp(-lambda)];
    for (let i = 1; i < 28; i++) a.push((a[i - 1] * lambda) / i);
    return a;
  };
  const h = poisson(rate('home')),
    a = poisson(rate('away'));
  let home = 0,
    draw = 0,
    away = 0;
  h.forEach((p, i) =>
    a.forEach((q, j) => {
      const d = stats.home.goals + i - stats.away.goals - j;
      if (d > 0) home += p * q;
      else if (d === 0) draw += p * q;
      else away += p * q;
    }),
  );
  const total = home + draw + away;
  return [home / total, draw / total, away / total];
}
