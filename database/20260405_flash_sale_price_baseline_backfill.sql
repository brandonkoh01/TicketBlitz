BEGIN;

UPDATE seat_categories AS sc
SET
    current_price = sc.base_price,
    updated_at = timezone('utc', now())
WHERE
    sc.deleted_at IS NULL
    AND sc.base_price IS NOT NULL
    AND sc.current_price IS DISTINCT FROM sc.base_price
    AND NOT EXISTS (
        SELECT 1
        FROM flash_sales AS fs
        WHERE
            fs.event_id = sc.event_id
            AND fs.status = 'ACTIVE'
            AND fs.ends_at > timezone('utc', now())
    );

COMMIT;
