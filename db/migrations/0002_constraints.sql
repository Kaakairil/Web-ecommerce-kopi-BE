-- 0002: dedupe cleanup, then unique constraints
-- cleanup: keep the oldest cart per user; drop duplicate cart items; drop duplicate emails (dev DB)
DELETE FROM carts c USING carts c2
  WHERE c.user_id = c2.user_id AND c.id > c2.id;

DELETE FROM cart_items ci USING cart_items ci2
  WHERE ci.cart_id = ci2.cart_id AND ci.product_id = ci2.product_id AND ci.id > ci2.id;

DELETE FROM transactions t USING transactions t2
  WHERE t.transaction_code = t2.transaction_code AND t.id > t2.id;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_carts_user_id') THEN
    ALTER TABLE carts ADD CONSTRAINT uq_carts_user_id UNIQUE (user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_cart_items_cart_product') THEN
    ALTER TABLE cart_items ADD CONSTRAINT uq_cart_items_cart_product UNIQUE (cart_id, product_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_transactions_code') THEN
    ALTER TABLE transactions ADD CONSTRAINT uq_transactions_code UNIQUE (transaction_code);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE indexname = 'uq_users_email'
  ) THEN
    CREATE UNIQUE INDEX uq_users_email ON users (lower(email));
  END IF;
END $$;
