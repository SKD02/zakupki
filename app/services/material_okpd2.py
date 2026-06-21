def ensure_material_okpd2_active_schema(cur):
    """
    Добавляет признак активной связи Material → OKPD2.

    Логика:
    - у материала может быть несколько ОКПД2;
    - активным может быть только один;
    - если активного ещё нет, первым встречающимся назначается первый mapping по физическому порядку строк.
    """
    cur.execute(
        """
        ALTER TABLE material_okpd2_map
        ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT false
        """
    )

    cur.execute(
        """
        UPDATE material_okpd2_map
        SET is_active = false
        WHERE is_active IS NULL
        """
    )

    # Если по материалу случайно несколько активных — оставляем только первый.
    cur.execute(
        """
        WITH active_ranked AS (
            SELECT
                ctid,
                row_number() OVER (
                    PARTITION BY btrim(material_id)
                    ORDER BY ctid
                ) AS rn
            FROM material_okpd2_map
            WHERE is_active = true
        )
        UPDATE material_okpd2_map mom
        SET is_active = false
        FROM active_ranked ar
        WHERE mom.ctid = ar.ctid
          AND ar.rn > 1
        """
    )

    # Если у материала есть mapping, но нет активного — активируем первый встречающийся.
    cur.execute(
        """
        WITH inactive_materials AS (
            SELECT DISTINCT btrim(mom.material_id) AS material_id
            FROM material_okpd2_map mom
            WHERE NOT EXISTS (
                SELECT 1
                FROM material_okpd2_map active_mom
                WHERE btrim(active_mom.material_id) = btrim(mom.material_id)
                  AND active_mom.is_active = true
            )
        ),
        ranked AS (
            SELECT
                mom.ctid,
                row_number() OVER (
                    PARTITION BY btrim(mom.material_id)
                    ORDER BY mom.ctid
                ) AS rn
            FROM material_okpd2_map mom
            JOIN inactive_materials im
                ON im.material_id = btrim(mom.material_id)
        )
        UPDATE material_okpd2_map mom
        SET is_active = true
        FROM ranked r
        WHERE mom.ctid = r.ctid
          AND r.rn = 1
        """
    )

    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_material_okpd2_map_one_active
        ON material_okpd2_map ((btrim(material_id)))
        WHERE is_active = true
        """
    )