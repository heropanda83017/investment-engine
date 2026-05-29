# IE-Cronjob-Fix — 2026-05-28

## Summary
- 6 prompt-based cronjobs: workdir cleared → now run from scheduler cwd
- 1 script-based cronjob: ie-daily-pipeline removed + recreated with correct workdir
- watchdog_check.py: hardcoded path patched (输出 -> output)

## Root Cause Discovery
Original diagnosis (Chinese paths blocking scheduler) was INCOMPLETE. 
Gateway (PID 12580) was running. Root cause: cron jobs were created but had never had a scheduler tick to fire on. Fix: ensure gateway active (it was) + cleanly configure workdir fields.

## Verification
- cronjob list: 10 jobs, all scheduled correctly
- watchdog manual trigger: next_run_at advanced to 2026-05-28T12:24:07
- V4 Pro FINAL REVIEW: APPROVED (41.8s, 4 LOW/INFO findings)

## V4 Pro Findings
1. LOW: path still mixed-language (output/02-投资研究) — cosmetic
2. INFO: 6 prompt jobs workdir-less — OK for inference-only
3. LOW: junction fragility — document if needed
4. INFO: monitor first execution cycle

## Files Changed
- watchdog_check.py: SYSTEM_DIR path patched
- 7 cronjobs: workdir resolved (6 cleared, 1 rebuilt)
