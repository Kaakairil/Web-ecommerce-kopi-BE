-- 0003: idempotency key on transactions
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_idempotency_key
  ON transactions (idempotency_key) WHERE idempotency_key IS NOT NULL;
