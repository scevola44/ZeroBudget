import { useEffect, useState } from "react";

const TICK_MS = 250;
const MS_PER_SECOND = 1000;

/** Whole seconds still to wait; rounds up so "0" only shows once the wait is truly over. */
export function secondsRemaining(totalSeconds: number, elapsedMs: number): number {
  return Math.max(Math.ceil(totalSeconds - elapsedMs / MS_PER_SECOND), 0);
}

/**
 * Seconds left of ``totalSeconds``, restarting whenever ``isActive`` turns on.
 * Based on elapsed wall-clock time rather than counting ticks, so a throttled
 * background tab can't make the wait shorter or longer than promised.
 */
export function useCountdown(totalSeconds: number, isActive: boolean): number {
  const [secondsLeft, setSecondsLeft] = useState(totalSeconds);

  useEffect(() => {
    if (!isActive) return;
    const startedAt = Date.now();
    setSecondsLeft(totalSeconds);
    const timer = setInterval(() => {
      const remaining = secondsRemaining(totalSeconds, Date.now() - startedAt);
      setSecondsLeft(remaining);
      if (remaining === 0) clearInterval(timer);
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [totalSeconds, isActive]);

  return secondsLeft;
}
