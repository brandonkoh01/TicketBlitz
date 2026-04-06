-- TicketBlitz additive seed: add 10 more catalogue events for website scale simulation.
-- Includes required easter egg names and minimal dependent rows for scenario dashboards.

begin;

set search_path = public, extensions;

insert into public.events (
  event_id,
  event_code,
  name,
  description,
  venue,
  event_date,
  booking_opens_at,
  booking_closes_at,
  total_capacity,
  status,
  metadata
) values
(
  '10000000-0000-0000-0000-000000000501',
  'EVT-501',
  'Richard Boone Asia Tour 2026',
  'Regional multi-city headline concert experience.',
  'Singapore Indoor Arena',
  '2026-07-12 20:00:00+08',
  '2026-04-15 09:00:00+08',
  '2026-07-12 19:00:00+08',
  8000,
  'ACTIVE',
  '{"seed":"bulk_events_20260405"}'::jsonb
),
(
  '10000000-0000-0000-0000-000000000502',
  'EVT-502',
  'Lawrence Wong Guitar Solo',
  'Live solo guitar showcase with orchestral backing.',
  'Esplanade Concert Hall',
  '2026-07-20 20:00:00+08',
  '2026-04-18 09:00:00+08',
  '2026-07-20 19:00:00+08',
  8000,
  'ACTIVE',
  '{"seed":"bulk_events_20260405"}'::jsonb
),
(
  '10000000-0000-0000-0000-000000000503',
  'EVT-503',
  'Arctic Pulse World Tour',
  'Electronic-pop arena performance with immersive visuals.',
  'National Stadium Singapore',
  '2026-08-03 20:00:00+08',
  '2026-04-22 09:00:00+08',
  '2026-08-03 19:00:00+08',
  8000,
  'ACTIVE',
  '{"seed":"bulk_events_20260405"}'::jsonb
),
(
  '10000000-0000-0000-0000-000000000504',
  'EVT-504',
  'Neon Skyline Live in Singapore',
  'Synthwave and dance anthem showcase.',
  'The Star Theatre',
  '2026-08-15 20:00:00+08',
  '2026-04-25 09:00:00+08',
  '2026-08-15 19:00:00+08',
  8000,
  'ACTIVE',
  '{"seed":"bulk_events_20260405"}'::jsonb
),
(
  '10000000-0000-0000-0000-000000000505',
  'EVT-505',
  'Midnight Atlas Reunion Show',
  'One-night reunion set featuring chart-topping classics.',
  'Capitol Theatre',
  '2026-08-29 20:00:00+08',
  '2026-04-29 09:00:00+08',
  '2026-08-29 19:00:00+08',
  8000,
  'ACTIVE',
  '{"seed":"bulk_events_20260405"}'::jsonb
),
(
  '10000000-0000-0000-0000-000000000506',
  'EVT-506',
  'Jade Horizon Acoustic Nights',
  'Acoustic arrangements and storyteller-style staging.',
  'Suntec Convention Hall',
  '2026-09-05 20:00:00+08',
  '2026-05-03 09:00:00+08',
  '2026-09-05 19:00:00+08',
  8000,
  'ACTIVE',
  '{"seed":"bulk_events_20260405"}'::jsonb
),
(
  '10000000-0000-0000-0000-000000000507',
  'EVT-507',
  'Ember Coast Festival Special',
  'Festival-format collaborative headline session.',
  'Marina Bay Open Stage',
  '2026-09-20 20:00:00+08',
  '2026-05-10 09:00:00+08',
  '2026-09-20 19:00:00+08',
  8000,
  'SCHEDULED',
  '{"seed":"bulk_events_20260405"}'::jsonb
),
(
  '10000000-0000-0000-0000-000000000508',
  'EVT-508',
  'The Meridian Strings Experience',
  'Orchestral-pop crossover with dynamic stage production.',
  'Victoria Theatre',
  '2026-10-04 20:00:00+08',
  '2026-05-14 09:00:00+08',
  '2026-10-04 19:00:00+08',
  8000,
  'SCHEDULED',
  '{"seed":"bulk_events_20260405"}'::jsonb
),
(
  '10000000-0000-0000-0000-000000000509',
  'EVT-509',
  'Aurora Signal Stadium Session',
  'Large-scale stadium set with synchronized light choreography.',
  'National Stadium Singapore',
  '2026-10-18 20:00:00+08',
  '2026-05-18 09:00:00+08',
  '2026-10-18 19:00:00+08',
  8000,
  'SCHEDULED',
  '{"seed":"bulk_events_20260405"}'::jsonb
),
(
  '10000000-0000-0000-0000-000000000510',
  'EVT-510',
  'Voltage Echoes Final Encore',
  'Farewell concert edition with extended encore set.',
  'Singapore Indoor Arena',
  '2026-11-02 20:00:00+08',
  '2026-05-22 09:00:00+08',
  '2026-11-02 19:00:00+08',
  8000,
  'SCHEDULED',
  '{"seed":"bulk_events_20260405"}'::jsonb
)
on conflict (event_id) do update
set
  event_code = excluded.event_code,
  name = excluded.name,
  description = excluded.description,
  venue = excluded.venue,
  event_date = excluded.event_date,
  booking_opens_at = excluded.booking_opens_at,
  booking_closes_at = excluded.booking_closes_at,
  total_capacity = excluded.total_capacity,
  status = excluded.status,
  metadata = excluded.metadata,
  deleted_at = null,
  updated_at = now();

insert into public.seat_categories (
  category_id,
  event_id,
  category_code,
  name,
  base_price,
  current_price,
  currency,
  total_seats,
  is_active,
  sort_order,
  metadata
) values
('20000000-0000-0000-0000-000000005011', '10000000-0000-0000-0000-000000000501', 'CAT1', 'Category 1', 188.00, 188.00, 'SGD', 3200, true, 10, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005012', '10000000-0000-0000-0000-000000000501', 'CAT2', 'Category 2', 138.00, 138.00, 'SGD', 2800, true, 20, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005013', '10000000-0000-0000-0000-000000000501', 'PEN', 'Pen', 268.00, 268.00, 'SGD', 2000, true, 30, '{"seed":"bulk_events_20260405"}'::jsonb),

('20000000-0000-0000-0000-000000005021', '10000000-0000-0000-0000-000000000502', 'CAT1', 'Category 1', 188.00, 188.00, 'SGD', 3200, true, 10, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005022', '10000000-0000-0000-0000-000000000502', 'CAT2', 'Category 2', 138.00, 138.00, 'SGD', 2800, true, 20, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005023', '10000000-0000-0000-0000-000000000502', 'PEN', 'Pen', 268.00, 268.00, 'SGD', 2000, true, 30, '{"seed":"bulk_events_20260405"}'::jsonb),

('20000000-0000-0000-0000-000000005031', '10000000-0000-0000-0000-000000000503', 'CAT1', 'Category 1', 188.00, 188.00, 'SGD', 3200, true, 10, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005032', '10000000-0000-0000-0000-000000000503', 'CAT2', 'Category 2', 138.00, 138.00, 'SGD', 2800, true, 20, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005033', '10000000-0000-0000-0000-000000000503', 'PEN', 'Pen', 268.00, 268.00, 'SGD', 2000, true, 30, '{"seed":"bulk_events_20260405"}'::jsonb),

('20000000-0000-0000-0000-000000005041', '10000000-0000-0000-0000-000000000504', 'CAT1', 'Category 1', 188.00, 188.00, 'SGD', 3200, true, 10, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005042', '10000000-0000-0000-0000-000000000504', 'CAT2', 'Category 2', 138.00, 138.00, 'SGD', 2800, true, 20, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005043', '10000000-0000-0000-0000-000000000504', 'PEN', 'Pen', 268.00, 268.00, 'SGD', 2000, true, 30, '{"seed":"bulk_events_20260405"}'::jsonb),

('20000000-0000-0000-0000-000000005051', '10000000-0000-0000-0000-000000000505', 'CAT1', 'Category 1', 188.00, 188.00, 'SGD', 3200, true, 10, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005052', '10000000-0000-0000-0000-000000000505', 'CAT2', 'Category 2', 138.00, 138.00, 'SGD', 2800, true, 20, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005053', '10000000-0000-0000-0000-000000000505', 'PEN', 'Pen', 268.00, 268.00, 'SGD', 2000, true, 30, '{"seed":"bulk_events_20260405"}'::jsonb),

('20000000-0000-0000-0000-000000005061', '10000000-0000-0000-0000-000000000506', 'CAT1', 'Category 1', 188.00, 188.00, 'SGD', 3200, true, 10, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005062', '10000000-0000-0000-0000-000000000506', 'CAT2', 'Category 2', 138.00, 138.00, 'SGD', 2800, true, 20, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005063', '10000000-0000-0000-0000-000000000506', 'PEN', 'Pen', 268.00, 268.00, 'SGD', 2000, true, 30, '{"seed":"bulk_events_20260405"}'::jsonb),

('20000000-0000-0000-0000-000000005071', '10000000-0000-0000-0000-000000000507', 'CAT1', 'Category 1', 188.00, 188.00, 'SGD', 3200, true, 10, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005072', '10000000-0000-0000-0000-000000000507', 'CAT2', 'Category 2', 138.00, 138.00, 'SGD', 2800, true, 20, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005073', '10000000-0000-0000-0000-000000000507', 'PEN', 'Pen', 268.00, 268.00, 'SGD', 2000, true, 30, '{"seed":"bulk_events_20260405"}'::jsonb),

('20000000-0000-0000-0000-000000005081', '10000000-0000-0000-0000-000000000508', 'CAT1', 'Category 1', 188.00, 188.00, 'SGD', 3200, true, 10, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005082', '10000000-0000-0000-0000-000000000508', 'CAT2', 'Category 2', 138.00, 138.00, 'SGD', 2800, true, 20, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005083', '10000000-0000-0000-0000-000000000508', 'PEN', 'Pen', 268.00, 268.00, 'SGD', 2000, true, 30, '{"seed":"bulk_events_20260405"}'::jsonb),

('20000000-0000-0000-0000-000000005091', '10000000-0000-0000-0000-000000000509', 'CAT1', 'Category 1', 188.00, 188.00, 'SGD', 3200, true, 10, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005092', '10000000-0000-0000-0000-000000000509', 'CAT2', 'Category 2', 138.00, 138.00, 'SGD', 2800, true, 20, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005093', '10000000-0000-0000-0000-000000000509', 'PEN', 'Pen', 268.00, 268.00, 'SGD', 2000, true, 30, '{"seed":"bulk_events_20260405"}'::jsonb),

('20000000-0000-0000-0000-000000005101', '10000000-0000-0000-0000-000000000510', 'CAT1', 'Category 1', 188.00, 188.00, 'SGD', 3200, true, 10, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005102', '10000000-0000-0000-0000-000000000510', 'CAT2', 'Category 2', 138.00, 138.00, 'SGD', 2800, true, 20, '{"seed":"bulk_events_20260405"}'::jsonb),
('20000000-0000-0000-0000-000000005103', '10000000-0000-0000-0000-000000000510', 'PEN', 'Pen', 268.00, 268.00, 'SGD', 2000, true, 30, '{"seed":"bulk_events_20260405"}'::jsonb)
on conflict (category_id) do update
set
  event_id = excluded.event_id,
  category_code = excluded.category_code,
  name = excluded.name,
  base_price = excluded.base_price,
  current_price = excluded.current_price,
  currency = excluded.currency,
  total_seats = excluded.total_seats,
  is_active = excluded.is_active,
  sort_order = excluded.sort_order,
  metadata = excluded.metadata,
  deleted_at = null,
  updated_at = now();

insert into public.inventory_event_state (
  event_id,
  flash_sale_active,
  active_flash_sale_id,
  last_sold_out_category,
  last_sold_out_at,
  metadata,
  updated_at
) values
('10000000-0000-0000-0000-000000000501', false, null, null, null, '{"seed":"bulk_events_20260405"}'::jsonb, now()),
('10000000-0000-0000-0000-000000000502', false, null, null, null, '{"seed":"bulk_events_20260405"}'::jsonb, now()),
('10000000-0000-0000-0000-000000000503', false, null, null, null, '{"seed":"bulk_events_20260405"}'::jsonb, now()),
('10000000-0000-0000-0000-000000000504', false, null, null, null, '{"seed":"bulk_events_20260405"}'::jsonb, now()),
('10000000-0000-0000-0000-000000000505', false, null, null, null, '{"seed":"bulk_events_20260405"}'::jsonb, now()),
('10000000-0000-0000-0000-000000000506', false, null, null, null, '{"seed":"bulk_events_20260405"}'::jsonb, now()),
('10000000-0000-0000-0000-000000000507', false, null, null, null, '{"seed":"bulk_events_20260405"}'::jsonb, now()),
('10000000-0000-0000-0000-000000000508', false, null, null, null, '{"seed":"bulk_events_20260405"}'::jsonb, now()),
('10000000-0000-0000-0000-000000000509', false, null, null, null, '{"seed":"bulk_events_20260405"}'::jsonb, now()),
('10000000-0000-0000-0000-000000000510', false, null, null, null, '{"seed":"bulk_events_20260405"}'::jsonb, now())
on conflict (event_id) do update
set
  flash_sale_active = excluded.flash_sale_active,
  active_flash_sale_id = excluded.active_flash_sale_id,
  last_sold_out_category = excluded.last_sold_out_category,
  last_sold_out_at = excluded.last_sold_out_at,
  metadata = excluded.metadata,
  updated_at = now();

commit;
