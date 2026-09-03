-- REQ-3.4 alternative to reset_batch.py — same 500-article reset.
-- Usage (replace :ids with your 500 IDs or use the temp table pattern):
--
--   psql $NEWS_DATABASE_URL -f eval/reset_batch.sql
--
-- This file resets the IDs listed in the literal array; generate the array with:
--   python eval/reset_batch.py --pick --out eval/bench_ids.txt
--   python -c "ids=open('eval/bench_ids.txt').read().split(); print('SELECT * FROM (VALUES (' + '),('.join(ids) + ')) t(id)')"
--
-- For a one-off quick reset of any 500 analyzed rows (non-reproducible — prefer the Python script):
--   UPDATE articles SET status='sentiment_done', started_at=NULL, retry_count=0, error_message=NULL, analyzed_at=NULL
--   WHERE id IN (SELECT id FROM articles WHERE status='analyzed' ORDER BY random() LIMIT 500);

-- Template: fill in your 500 IDs from eval/bench_ids.txt
-- UPDATE articles SET status='sentiment_done', started_at=NULL, retry_count=0, error_message=NULL, analyzed_at=NULL
-- WHERE id = ANY(ARRAY[1,2,3 /* ... 500 ids ... */]::int[]);

-- Verify REQ-3.5 invariant (should equal 500 during a benchmark run):
-- SELECT count(*) AS sentiment_done_count FROM articles WHERE status='sentiment_done';
