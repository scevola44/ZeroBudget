const MS_PER_SECOND = 1000;

/** Whole seconds still to wait; rounds up so "0" only shows once the wait is truly over. */
export function secondsRemaining(totalSeconds: number, elapsedMs: number): number {
  return Math.max(Math.ceil(totalSeconds - elapsedMs / MS_PER_SECOND), 0);
}
