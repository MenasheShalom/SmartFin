import assert from 'node:assert/strict';
import { test } from 'node:test';

import { isDue, lastOccurrence, msUntilNext } from '../src/schedule.js';

const HOUR = 60 * 60 * 1000;

test('waits until later today', () => {
  assert.equal(msUntilNext('03:00', new Date(2026, 8, 24, 1, 0)), 2 * HOUR);
});

test('rolls over to tomorrow once the time has passed', () => {
  assert.equal(msUntilNext('03:00', new Date(2026, 8, 24, 3, 0)), 24 * HOUR);
  assert.equal(msUntilNext('03:00', new Date(2026, 8, 24, 4, 30)), 22.5 * HOUR);
});

test('a run is due once HH:MM has passed since the last one', () => {
  const lastRun = new Date(2026, 9, 1, 14, 0);
  assert.equal(isDue('03:00', lastRun, new Date(2026, 9, 1, 23, 0)), false);
  assert.equal(isDue('03:00', lastRun, new Date(2026, 9, 2, 2, 59)), false);
  assert.equal(isDue('03:00', lastRun, new Date(2026, 9, 2, 3, 0)), true);
});

test('a run missed while the machine slept is due on waking, once', () => {
  const lastRun = new Date(2026, 9, 1, 3, 5);
  const wake = new Date(2026, 9, 7, 18, 0);
  assert.equal(isDue('03:00', lastRun, wake), true);
  assert.equal(isDue('03:00', wake, new Date(2026, 9, 7, 18, 1)), false);
  assert.deepEqual(lastOccurrence('03:00', wake), new Date(2026, 9, 7, 3, 0));
});
