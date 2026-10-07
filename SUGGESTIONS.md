# Suggestions for later

Improvements we have discussed and chosen not to build in the current prototype.

## LLM pass for near-miss dedup

Dedup stays a deterministic fingerprint: service, normalized message, and the top stack frames. The same hash always attaches to the open incident.

A later pass can ask Claude whether an incoming error is the same failure as an open incident when the wording or stack has shifted enough to miss the hash. Reordered messages and a moved stack frame are the cases this is for.

The order stays fixed:

1. A fingerprint match counts the sample and stops. The model does not split that match.
2. A new fingerprint may be compared with other open incidents and attached to one of them.
3. Otherwise a new incident is opened.

Category and severity classification is separate. It does not decide whether the error is new.
