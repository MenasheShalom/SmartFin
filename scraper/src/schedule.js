// The nightly scrape, decided by the wall clock (the container runs with TZ=Asia/Jerusalem).
//
// One long setTimeout until HH:MM is not enough: on a laptop or a Windows/macOS Docker host the
// machine sleeps, timers only count awake time, and the run never comes. Instead main.js checks
// every minute whether a run is due, so a run missed while asleep happens on waking.

// Milliseconds from `now` until the next local HH:MM; for the log line.
export function msUntilNext(time, now = new Date()) {
  const [hours, minutes] = time.split(':').map(Number);
  const next = new Date(now);
  next.setHours(hours, minutes, 0, 0);
  if (next <= now) next.setDate(next.getDate() + 1);
  return next - now;
}

// The latest local HH:MM at or before `now`.
export function lastOccurrence(time, now = new Date()) {
  const [hours, minutes] = time.split(':').map(Number);
  const last = new Date(now);
  last.setHours(hours, minutes, 0, 0);
  if (last > now) last.setDate(last.getDate() - 1);
  return last;
}

// Due when an HH:MM has passed since the last run (however long ago that was).
export function isDue(time, lastRun, now = new Date()) {
  return lastOccurrence(time, now) > lastRun;
}
