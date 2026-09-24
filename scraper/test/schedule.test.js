import assert from 'node:assert/strict';
import { test } from 'node:test';

import { msUntilNext } from '../src/schedule.js';

const HOUR = 60 * 60 * 1000;

test('waits until later today', () => {
  assert.equal(msUntilNext('03:00', new Date(2026, 8, 24, 1, 0)), 2 * HOUR);
});

test('rolls over to tomorrow once the time has passed', () => {
  assert.equal(msUntilNext('03:00', new Date(2026, 8, 24, 3, 0)), 24 * HOUR);
  assert.equal(msUntilNext('03:00', new Date(2026, 8, 24, 4, 30)), 22.5 * HOUR);
});
