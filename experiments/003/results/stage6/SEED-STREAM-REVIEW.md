# Pre-StudyB seed-stream review

Discovered by algebraic source inspection while StudyA was running. Only validity status has been viewed; no secondary numeric outcome analysis has run and no StudyB traffic has executed at discovery.

Original seed_j = master + j*gamma modulo2^64; SplitMix64 advances state by gamma=0x9e3779b97f4a7c15. Therefore state(client j, draw2) = state(client j+1, draw1). The clients have distinct seeds/processes but their underlying random sequences overlap as phase shifts. Different rejection/cap histories do not repair this avoidable joint-stream dependence. H6 should not be presented as a comparison against independently seeded jitter streams under that derivation.

Minimal resolution before StudyB: keep master seeds, order, workload, compiled binaries, guards and all algorithm parameters; derive each client seed from SHA256(domain || master || client), record exact byte encoding and versioned plan. Preserve original RUN-PLAN and source/freeze/evidence. Finish StudyA unchanged; stop the original driver at the A/B boundary, preserve any intercepted startup attempt with an explicit exclusion reason and verify whether any traffic occurred. Freeze and execute the amended B plan separately. No unfavorable valid outcome motivates this correction.

The original plan is not silently edited. A dated/versioned amendment, source/freeze and separate matrix will be recorded; all original attempts remain reviewable. Never pool a correlated-stream B run with amended independent-seed pairs.
