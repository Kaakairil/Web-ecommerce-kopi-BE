-- 0004: RLS enabled on all user tables; service-role (backend) bypasses RLS,
-- anon/public cannot read anything.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE stocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE carts ENABLE ROW LEVEL SECURITY;
ALTER TABLE cart_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE transaction_items ENABLE ROW LEVEL SECURITY;

-- Drop conflicting policies if re-run
DROP POLICY IF EXISTS deny_anon_all ON users;
DROP POLICY IF EXISTS deny_anon_all ON products;
DROP POLICY IF EXISTS deny_anon_all ON stocks;
DROP POLICY IF EXISTS deny_anon_all ON carts;
DROP POLICY IF EXISTS deny_anon_all ON cart_items;
DROP POLICY IF EXISTS deny_anon_all ON transactions;
DROP POLICY IF EXISTS deny_anon_all ON transaction_items;

-- No permissive policies = anon/authenticated get zero rows.
-- service_role connection (the backend) bypasses RLS entirely.
CREATE POLICY deny_anon_all ON users FOR SELECT TO anon USING (false);
CREATE POLICY deny_anon_all ON products FOR SELECT TO anon USING (false);
CREATE POLICY deny_anon_all ON stocks FOR SELECT TO anon USING (false);
CREATE POLICY deny_anon_all ON carts FOR SELECT TO anon USING (false);
CREATE POLICY deny_anon_all ON cart_items FOR SELECT TO anon USING (false);
CREATE POLICY deny_anon_all ON transactions FOR SELECT TO anon USING (false);
CREATE POLICY deny_anon_all ON transaction_items FOR SELECT TO anon USING (false);
