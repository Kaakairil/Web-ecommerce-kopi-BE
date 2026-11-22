-- 0005: atomic idempotent checkout RPC
-- Contract (jsonb payload in, jsonb result out):
--   payload: {"user_id": int, "idempotency_key": text, "payment_method": text,
--             "shipping_address": text, "notes": text}
--   ok:      {"ok": true, "transaction": {...}, "shipping_fee": numeric}
--   replay:  {"ok": true, "transaction": {...}, "idempotent_replay": true}
--   error:   {"ok": false, "error": "INSUFFICIENT_STOCK", "product": name, "available": n}
--            {"ok": false, "error": "EMPTY_CART"}
-- Shipping: flat Rp 15000 when subtotal < 250000, free (0) otherwise.
CREATE OR REPLACE FUNCTION checkout_transaction(payload JSONB)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
  v_user_id        INT;
  v_idem_key       TEXT;
  v_cart           RECORD;
  v_item           RECORD;
  v_product        RECORD;
  v_stock          RECORD;
  v_subtotal       NUMERIC := 0;
  v_shipping_fee   NUMERIC := 0;
  v_total          NUMERIC := 0;
  v_transaction_id BIGINT;
  v_code           TEXT;
  v_existing       transactions%ROWTYPE;
BEGIN
  v_user_id  := (payload->>'user_id')::INT;
  v_idem_key := payload->>'idempotency_key';

  -- Idempotency: if the key already produced a transaction, return it untouched.
  IF v_idem_key IS NOT NULL THEN
    SELECT * INTO v_existing FROM transactions WHERE idempotency_key = v_idem_key;
    IF FOUND THEN
      RETURN jsonb_build_object(
        'ok', true,
        'idempotent_replay', true,
        'transaction', to_jsonb(v_existing)
      );
    END IF;
  END IF;

  SELECT * INTO v_cart FROM carts WHERE user_id = v_user_id;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'error', 'EMPTY_CART');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM cart_items WHERE cart_id = v_cart.id) THEN
    RETURN jsonb_build_object('ok', false, 'error', 'EMPTY_CART');
  END IF;

  -- Validate stock and compute subtotal.
  FOR v_item IN
    SELECT ci.product_id, ci.quantity
    FROM cart_items ci WHERE ci.cart_id = v_cart.id
  LOOP
    SELECT * INTO v_product FROM products WHERE id = v_item.product_id;
    IF NOT FOUND OR v_product.is_available IS NOT TRUE THEN
      RETURN jsonb_build_object('ok', false, 'error', 'PRODUCT_UNAVAILABLE',
                                'product', v_product.name);
    END IF;

    SELECT * INTO v_stock FROM stocks WHERE product_id = v_item.product_id FOR UPDATE;
    IF NOT FOUND OR v_stock.quantity < v_item.quantity THEN
      RETURN jsonb_build_object('ok', false, 'error', 'INSUFFICIENT_STOCK',
                                'product', v_product.name,
                                'available', COALESCE(v_stock.quantity, 0));
    END IF;

    v_subtotal := v_subtotal + (v_product.price * v_item.quantity);
  END LOOP;

  -- Shipping rule: flat 15000 below 250000, free above.
  IF v_subtotal < 250000 THEN
    v_shipping_fee := 15000;
  END IF;
  v_total := v_subtotal + v_shipping_fee;

  v_code := 'TRX-' || to_char(now() AT TIME ZONE 'UTC', 'YYYYMMDD') || '-' ||
            upper(substr(md5(random()::text || clock_timestamp()::text), 1, 6));

  INSERT INTO transactions
    (transaction_code, user_id, total_amount, status, payment_method,
     shipping_address, notes, idempotency_key, created_at, updated_at)
  VALUES
    (v_code, v_user_id, v_total, 'pending',
     COALESCE(payload->>'payment_method', 'Bank Transfer'),
     COALESCE(payload->>'shipping_address', ''),
     COALESCE(payload->>'notes', ''),
     v_idem_key, now(), now())
  RETURNING id INTO v_transaction_id;

  -- Decrement stock (locked above) + write items + outbox event.
  FOR v_item IN
    SELECT ci.product_id, ci.quantity FROM cart_items ci WHERE ci.cart_id = v_cart.id
  LOOP
    SELECT * INTO v_product FROM products WHERE id = v_item.product_id;

    UPDATE stocks
       SET quantity = quantity - v_item.quantity, updated_at = now()
     WHERE product_id = v_item.product_id;

    INSERT INTO transaction_items
      (transaction_id, product_id, quantity, price, subtotal, created_at)
    VALUES
      (v_transaction_id, v_item.product_id, v_item.quantity,
       v_product.price, v_product.price * v_item.quantity, now());
  END LOOP;

  INSERT INTO events (event_type, payload, status, created_at)
  VALUES ('order.created',
          jsonb_build_object('transaction_id', v_transaction_id,
                             'transaction_code', v_code,
                             'user_id', v_user_id,
                             'total_amount', v_total),
          'pending', now());

  DELETE FROM cart_items WHERE cart_id = v_cart.id;

  RETURN jsonb_build_object(
    'ok', true,
    'shipping_fee', v_shipping_fee,
    'transaction', to_jsonb(
      (SELECT t FROM transactions t WHERE t.id = v_transaction_id))
  );
END;
$$;
