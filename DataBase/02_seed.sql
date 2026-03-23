INSERT INTO users (email, full_name, role)
VALUES
  ('ayinde@hampton.edu', 'Ayinde Hooks', 'student'),
  ('seller@hampton.edu', 'Sample Seller', 'student')
ON CONFLICT (email) DO NOTHING;

INSERT INTO listings (seller_id, title, description, price_cents, category, status)
SELECT u.id, 'Mini Fridge', 'Works great, need gone ASAP.', 4500, 'appliances', 'active'
FROM users u
WHERE u.email = 'seller@hampton.edu';

INSERT INTO listing_images (listing_id, image_url)
SELECT l.id, 'https://example.com/fridge.png'
FROM listings l
WHERE l.title = 'Mini Fridge';
