// Milliseconds from `now` until the next local HH:MM (the container runs with TZ=Asia/Jerusalem).
export function msUntilNext(time, now = new Date()) {
  const [hours, minutes] = time.split(':').map(Number);
  const next = new Date(now);
  next.setHours(hours, minutes, 0, 0);
  if (next <= now) next.setDate(next.getDate() + 1);
  return next - now;
}
