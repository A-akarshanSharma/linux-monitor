// Cross-references a metric or service against the current alerts list, so stat
// cards and the disk/service lists can reuse the backend's own judgement of
// what's wrong instead of re-implementing threshold logic in the frontend.

/**
 * The backend's AlertState is WARNING | CRITICAL | RESOLVED (see the Phase 4
 * README notes: NORMAL is the absence of a row, never a stored value). This
 * returns that same vocabulary, plus 'normal' for "no matching open alert" -
 * the frontend's equivalent of NORMAL.
 */
export function severityFor(alerts, ruleKey, target = '') {
  const match = alerts?.find(
    (alert) => alert.rule_key === ruleKey && alert.target === target && alert.state !== 'RESOLVED',
  )
  return match ? match.state.toLowerCase() : 'normal'
}
