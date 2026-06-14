# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel, Field

# from app.database import get_connection, fetch_all, fetch_one
# from app.services.email_sender import build_procurement_email, extract_emails, send_email_smtp

# router = APIRouter()


# class SendEmailsRequest(BaseModel):
#     batch_ids: list[int] = Field(default_factory=list)


# def ensure_email_log_table(cur):
#     cur.execute(
#         """
#         CREATE TABLE IF NOT EXISTS procurement_email_logs (
#             log_id bigserial PRIMARY KEY,
#             batch_id int8 NOT NULL REFERENCES procurement_email_batches(batch_id) ON DELETE CASCADE,
#             supplier_inn text NULL,
#             supplier_name text NULL,
#             recipient_email text NULL,
#             subject text NULL,
#             body text NULL,
#             status text NOT NULL,
#             error_message text NULL,
#             sent_at timestamptz DEFAULT now() NOT NULL,
#             created_at timestamptz DEFAULT now() NOT NULL
#         )
#         """
#     )
#     cur.execute(
#         """
#         CREATE INDEX IF NOT EXISTS idx_procurement_email_logs_batch_id
#         ON procurement_email_logs(batch_id)
#         """
#     )
#     cur.execute(
#         """
#         ALTER TABLE procurement_email_batches
#         ADD COLUMN IF NOT EXISTS kp_request_id integer,
#         ADD COLUMN IF NOT EXISTS kp_request_code text
#         """
#     )
#     cur.execute(
#         """
#         CREATE INDEX IF NOT EXISTS idx_procurement_email_batches_kp_request_id
#         ON procurement_email_batches(kp_request_id)
#         """
#     )


# def ensure_email_log_schema():
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             ensure_email_log_table(cur)
#             conn.commit()


# @router.post("/application/{application_id}/generate")
# def generate_batches(application_id: int):
#     conn = get_connection()

#     try:
#         with conn:
#             with conn.cursor() as cur:
#                 # 1. Проверяем, есть ли результаты поиска поставщиков
#                 cur.execute(
#                     """
#                     SELECT COUNT(*) AS cnt
#                     FROM supplier_search_results r
#                     JOIN purchase_application_items i
#                         ON i.item_id = r.item_id
#                     WHERE i.application_id = %s
#                     """,
#                     (application_id,),
#                 )
#                 search_results_count = cur.fetchone()["cnt"]

#                 if search_results_count == 0:
#                     return {
#                         "status": "NO_SUPPLIER_RESULTS",
#                         "message": "Нельзя сформировать черновики: сначала выполните подбор поставщиков. Сейчас результатов подбора нет.",
#                         "batches": [],
#                     }

#                 # 2. Удаляем старые черновики по заявке
#                 cur.execute(
#                     """
#                     DELETE FROM procurement_email_batches
#                     WHERE application_id = %s
#                     """,
#                     (application_id,),
#                 )

#                 # 3. Собираем группы для черновиков
#                 cur.execute(
#                     """
#                     SELECT
#                         i.application_id,
#                         r.supplier_id,
#                         r.supplier_inn,
#                         r.supplier_name,
#                         r.search_method,
#                         r.okpd2_code,
#                         r.okved2_code,
#                         r.user_group_id,
#                         MIN(i.supply_start_date) AS supply_start_date,
#                         MAX(i.supply_end_date) AS supply_end_date,
#                         COUNT(DISTINCT r.item_id) AS items_count
#                     FROM supplier_search_results r
#                     JOIN purchase_application_items i
#                         ON i.item_id = r.item_id
#                     WHERE i.application_id = %s
#                     GROUP BY
#                         i.application_id,
#                         r.supplier_id,
#                         r.supplier_inn,
#                         r.supplier_name,
#                         r.search_method,
#                         r.okpd2_code,
#                         r.okved2_code,
#                         r.user_group_id
#                     HAVING COUNT(DISTINCT r.item_id) > 0
#                     """,
#                     (application_id,),
#                 )

#                 groups = cur.fetchall()

#                 if len(groups) == 0:
#                     return {
#                         "status": "NO_BATCH_GROUPS",
#                         "message": "Не удалось сформировать группы для черновиков писем. Проверьте результаты подбора поставщиков.",
#                         "batches": [],
#                     }

#                 created_batches = 0

#                 for group in groups:
#                     # Не создаем черновик, если вообще нет поставщика
#                     if not group["supplier_id"] and not group["supplier_inn"] and not group["supplier_name"]:
#                         continue

#                     cur.execute(
#                         """
#                         INSERT INTO procurement_email_batches (
#                             application_id,
#                             supplier_id,
#                             supplier_inn,
#                             supplier_name,
#                             search_method,
#                             okpd2_code,
#                             okved2_code,
#                             user_group_id,
#                             supply_start_date,
#                             supply_end_date,
#                             status
#                         )
#                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DRAFT')
#                         RETURNING batch_id
#                         """,
#                         (
#                             group["application_id"],
#                             group["supplier_id"],
#                             group["supplier_inn"],
#                             group["supplier_name"],
#                             group["search_method"],
#                             group["okpd2_code"],
#                             group["okved2_code"],
#                             group["user_group_id"],
#                             group["supply_start_date"],
#                             group["supply_end_date"],
#                         ),
#                     )

#                     batch_id = cur.fetchone()["batch_id"]

#                     cur.execute(
#                         """
#                         INSERT INTO procurement_email_batch_items (
#                             batch_id,
#                             item_id
#                         )
#                         SELECT DISTINCT
#                             %s,
#                             r.item_id
#                         FROM supplier_search_results r
#                         JOIN purchase_application_items i
#                             ON i.item_id = r.item_id
#                         WHERE i.application_id = %s
#                           AND COALESCE(r.supplier_id::text, '') = COALESCE(%s::text, '')
#                           AND COALESCE(r.supplier_inn, '') = COALESCE(%s, '')
#                           AND COALESCE(r.supplier_name, '') = COALESCE(%s, '')
#                           AND r.search_method = %s
#                           AND COALESCE(r.okpd2_code, '') = COALESCE(%s, '')
#                           AND COALESCE(r.okved2_code, '') = COALESCE(%s, '')
#                           AND COALESCE(r.user_group_id, '') = COALESCE(%s, '')
#                         """,
#                         (
#                             batch_id,
#                             application_id,
#                             group["supplier_id"],
#                             group["supplier_inn"],
#                             group["supplier_name"],
#                             group["search_method"],
#                             group["okpd2_code"],
#                             group["okved2_code"],
#                             group["user_group_id"],
#                         ),
#                     )

#                     cur.execute(
#                         """
#                         SELECT COUNT(*) AS cnt
#                         FROM procurement_email_batch_items
#                         WHERE batch_id = %s
#                         """,
#                         (batch_id,),
#                     )
#                     batch_items_count = cur.fetchone()["cnt"]

#                     if batch_items_count == 0:
#                         cur.execute(
#                             """
#                             DELETE FROM procurement_email_batches
#                             WHERE batch_id = %s
#                             """,
#                             (batch_id,),
#                         )
#                     else:
#                         created_batches += 1

#                 if created_batches == 0:
#                     return {
#                         "status": "NO_BATCHES_CREATED",
#                         "message": "Черновики писем не сформированы: нет валидных поставщиков или позиций для группировки.",
#                         "batches": [],
#                     }

#                 cur.execute(
#                     """
#                     UPDATE purchase_application_items
#                     SET processing_status = 'EMAIL_PREPARED',
#                         updated_at = now()
#                     WHERE application_id = %s
#                       AND item_id IN (
#                           SELECT bi.item_id
#                           FROM procurement_email_batch_items bi
#                           JOIN procurement_email_batches b
#                               ON b.batch_id = bi.batch_id
#                           WHERE b.application_id = %s
#                       )
#                     """,
#                     (application_id, application_id),
#                 )

#         batches = get_application_batches(application_id)

#         return {
#             "status": "OK",
#             "message": f"Черновики писем сформированы. Создано черновиков: {len(batches)}",
#             "batches": batches,
#         }

#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Ошибка формирования черновиков писем: {str(e)}"
#         )

#     finally:
#         conn.close()


# @router.get("/application/{application_id}")
# def get_application_batches(application_id: int):
#     ensure_email_log_schema()
#     return fetch_all("""
#         SELECT
#             b.*,
#             s.email AS supplier_email,
#             COUNT(DISTINCT bi.item_id) AS items_count,
#             COUNT(DISTINCT l.log_id) FILTER (WHERE l.status = 'SENT') AS sent_logs_count,
#             MAX(l.sent_at) AS last_sent_at
#         FROM procurement_email_batches b
#         LEFT JOIN procurement_email_batch_items bi
#             ON bi.batch_id = b.batch_id
#         LEFT JOIN suppliers s
#             ON s.inn = b.supplier_inn
#         LEFT JOIN procurement_email_logs l
#             ON l.batch_id = b.batch_id
#         WHERE b.application_id = %s
#         GROUP BY b.batch_id, s.email
#         ORDER BY
#             b.search_method,
#             b.supplier_name,
#             b.supplier_inn
#     """, (application_id,))


# @router.get("/{batch_id}")
# def get_batch(batch_id: int):
#     ensure_email_log_schema()
#     batch = fetch_one("""
#         SELECT b.*, s.email AS supplier_email
#         FROM procurement_email_batches b
#         LEFT JOIN suppliers s ON s.inn = b.supplier_inn
#         WHERE b.batch_id=%s
#     """, (batch_id,))
#     if not batch:
#         raise HTTPException(status_code=404, detail="Черновик письма не найден")
#     items = fetch_all("""
#         SELECT
#             a.application_no,
#             a.application_date,
#             a.construction_object,
#             i.*
#         FROM procurement_email_batch_items bi
#         JOIN purchase_application_items i
#             ON i.item_id = bi.item_id
#         JOIN purchase_applications a
#             ON a.application_id = i.application_id
#         WHERE bi.batch_id = %s
#         ORDER BY
#             a.application_id,
#             i.material_name
#     """, (batch_id,))
#     logs = fetch_all("""
#         SELECT log_id, recipient_email, subject, status, error_message, sent_at
#         FROM procurement_email_logs
#         WHERE batch_id = %s
#         ORDER BY sent_at DESC
#     """, (batch_id,))
#     subject, body = build_procurement_email(batch, items)
#     return {"batch": batch, "items": items, "logs": logs, "email_preview": {"subject": subject, "body": body}}


# @router.post("/send-emails")
# def send_selected_emails(payload: SendEmailsRequest):
#     batch_ids = list(dict.fromkeys(payload.batch_ids))
#     if not batch_ids:
#         raise HTTPException(status_code=400, detail="Выберите хотя бы один черновик письма для отправки")

#     conn = get_connection()
#     results = []

#     try:
#         with conn:
#             with conn.cursor() as cur:
#                 ensure_email_log_table(cur)

#         for batch_id in batch_ids:
#             batch = fetch_one("""
#                 SELECT b.*, s.email AS supplier_email
#                 FROM procurement_email_batches b
#                 LEFT JOIN suppliers s ON s.inn = b.supplier_inn
#                 WHERE b.batch_id = %s
#             """, (batch_id,))

#             if not batch:
#                 results.append({"batch_id": batch_id, "status": "ERROR", "message": "Черновик не найден"})
#                 continue

#             items = fetch_all("""
#                 SELECT
#                     a.application_no,
#                     a.application_date,
#                     a.construction_object,
#                     i.*
#                 FROM procurement_email_batch_items bi
#                 JOIN purchase_application_items i
#                     ON i.item_id = bi.item_id
#                 JOIN purchase_applications a
#                     ON a.application_id = i.application_id
#                 WHERE bi.batch_id = %s
#                 ORDER BY
#                     a.application_id,
#                     i.material_name
#             """, (batch_id,))

#             to_emails = extract_emails(batch.get("supplier_email"))
#             subject, body = build_procurement_email(batch, items)
#             status = "SENT"
#             error_message = None

#             try:
#                 send_email_smtp(to_emails, subject, body)
#             except Exception as exc:
#                 status = "ERROR"
#                 error_message = str(exc)

#             with get_connection() as log_conn:
#                 with log_conn.cursor() as cur:
#                     ensure_email_log_table(cur)
#                     cur.execute(
#                         """
#                         INSERT INTO procurement_email_logs (
#                             batch_id,
#                             supplier_inn,
#                             supplier_name,
#                             recipient_email,
#                             subject,
#                             body,
#                             status,
#                             error_message
#                         ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
#                         """,
#                         (
#                             batch_id,
#                             batch.get("supplier_inn"),
#                             batch.get("supplier_name"),
#                             ", ".join(to_emails),
#                             subject,
#                             body,
#                             status,
#                             error_message,
#                         ),
#                     )
#                     cur.execute(
#                         """
#                         UPDATE procurement_email_batches
#                         SET status = %s, updated_at = now()
#                         WHERE batch_id = %s
#                         """,
#                         ("SENT" if status == "SENT" else "SEND_ERROR", batch_id),
#                     )
#                     if status == "SENT":
#                         cur.execute(
#                             """
#                             UPDATE purchase_application_items
#                             SET processing_status = 'EMAIL_SENT', updated_at = now()
#                             WHERE item_id IN (
#                                 SELECT item_id FROM procurement_email_batch_items WHERE batch_id = %s
#                             )
#                             """,
#                             (batch_id,),
#                         )
#                     log_conn.commit()

#             results.append({
#                 "batch_id": batch_id,
#                 "status": status,
#                 "recipient_email": ", ".join(to_emails),
#                 "message": "Письмо отправлено" if status == "SENT" else error_message,
#             })

#         sent_count = sum(1 for result in results if result["status"] == "SENT")
#         error_count = sum(1 for result in results if result["status"] != "SENT")
#         return {
#             "status": "OK" if error_count == 0 else "PARTIAL" if sent_count else "ERROR",
#             "sent_count": sent_count,
#             "error_count": error_count,
#             "results": results,
#         }

#     finally:
#         conn.close()


# @router.get("/email-logs/recent")
# def get_recent_email_logs(limit: int = 100):
#     limit = max(1, min(limit, 500))
#     ensure_email_log_schema()
#     return fetch_all("""
#         SELECT l.log_id, l.batch_id, b.application_id, b.kp_request_code, l.supplier_inn, l.supplier_name,
#                l.recipient_email, l.subject, l.status, l.error_message, l.sent_at
#         FROM procurement_email_logs l
#         LEFT JOIN procurement_email_batches b ON b.batch_id = l.batch_id
#         ORDER BY l.sent_at DESC
#         LIMIT %s
#     """, (limit,))

# @router.get("")
# def get_all_batches(limit: int = 500):
#     ensure_email_log_schema()
#     limit = max(1, min(limit, 2000))

#     return fetch_all(
#         """
#         SELECT
#             b.*,
#             s.email AS supplier_email,
#             COUNT(DISTINCT bi.item_id) AS items_count,
#             COUNT(DISTINCT i.application_id) AS applications_count,
#             COUNT(DISTINCT l.log_id) FILTER (WHERE l.status = 'SENT') AS sent_logs_count,
#             MAX(l.sent_at) AS last_sent_at
#         FROM procurement_email_batches b
#         LEFT JOIN procurement_email_batch_items bi
#             ON bi.batch_id = b.batch_id
#         LEFT JOIN purchase_application_items i
#             ON i.item_id = bi.item_id
#         LEFT JOIN suppliers s
#             ON s.inn = b.supplier_inn
#         LEFT JOIN procurement_email_logs l
#             ON l.batch_id = b.batch_id
#         GROUP BY b.batch_id, s.email
#         ORDER BY
#             b.created_at DESC,
#             b.search_method,
#             b.supplier_name,
#             b.supplier_inn
#         LIMIT %s
#         """,
#         (limit,),
#     )

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import get_connection, fetch_all, fetch_one
from app.services.email_sender import build_procurement_email, extract_emails, send_email_smtp

router = APIRouter()


class SendEmailsRequest(BaseModel):
    batch_ids: list[int] = Field(default_factory=list)


def ensure_email_log_table(cur):
    cur.execute("CREATE SEQUENCE IF NOT EXISTS kp_request_seq START 1")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS kp_requests (
            kp_request_id integer PRIMARY KEY DEFAULT nextval('kp_request_seq'),
            kp_request_code text UNIQUE NOT NULL,
            status text DEFAULT 'SUPPLIERS_SEARCHED',
            filter_payload jsonb,
            created_at timestamptz DEFAULT now(),
            updated_at timestamptz DEFAULT now()
        )
        """)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS procurement_email_logs (
            log_id bigserial PRIMARY KEY,
            batch_id int8 NOT NULL REFERENCES procurement_email_batches(batch_id) ON DELETE CASCADE,
            supplier_inn text NULL,
            supplier_name text NULL,
            recipient_email text NULL,
            subject text NULL,
            body text NULL,
            status text NOT NULL,
            error_message text NULL,
            sent_at timestamptz DEFAULT now() NOT NULL,
            created_at timestamptz DEFAULT now() NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procurement_email_logs_batch_id
        ON procurement_email_logs(batch_id)
        """
    )
    cur.execute(
        """
        ALTER TABLE procurement_email_batches
        ADD COLUMN IF NOT EXISTS kp_request_id integer,
        ADD COLUMN IF NOT EXISTS kp_request_code text
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procurement_email_batches_kp_request_id
        ON procurement_email_batches(kp_request_id)
        """
    )



def refresh_kp_request_status(cur, kp_request_id: int):
    if not kp_request_id:
        return

    cur.execute(
        """
        UPDATE kp_requests kr
        SET status = CASE
                WHEN COALESCE(stats.total_batches, 0) = 0 THEN kr.status
                WHEN stats.sent_batches = stats.total_batches THEN 'EMAIL_SENT'
                WHEN stats.sent_batches > 0 THEN 'PARTIALLY_SENT'
                WHEN stats.error_batches > 0 THEN 'SEND_ERROR'
                ELSE 'EMAIL_PREPARED'
            END,
            updated_at = now()
        FROM (
            SELECT
                kp_request_id,
                COUNT(*) AS total_batches,
                COUNT(*) FILTER (WHERE status = 'SENT') AS sent_batches,
                COUNT(*) FILTER (WHERE status = 'SEND_ERROR') AS error_batches
            FROM procurement_email_batches
            WHERE kp_request_id = %s
            GROUP BY kp_request_id
        ) stats
        WHERE kr.kp_request_id = stats.kp_request_id
          AND kr.kp_request_id = %s
        """,
        (kp_request_id, kp_request_id),
    )

def ensure_email_log_schema():
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_email_log_table(cur)
            conn.commit()


@router.post("/application/{application_id}/generate")
def generate_batches(application_id: int):
    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Проверяем, есть ли результаты поиска поставщиков
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM supplier_search_results r
                    JOIN purchase_application_items i
                        ON i.item_id = r.item_id
                    WHERE i.application_id = %s
                    """,
                    (application_id,),
                )
                search_results_count = cur.fetchone()["cnt"]

                if search_results_count == 0:
                    return {
                        "status": "NO_SUPPLIER_RESULTS",
                        "message": "Нельзя сформировать черновики: сначала выполните подбор поставщиков. Сейчас результатов подбора нет.",
                        "batches": [],
                    }

                # 2. Удаляем старые черновики по заявке
                cur.execute(
                    """
                    DELETE FROM procurement_email_batches
                    WHERE application_id = %s
                    """,
                    (application_id,),
                )

                # 3. Собираем группы для черновиков
                cur.execute(
                    """
                    SELECT
                        i.application_id,
                        r.supplier_id,
                        r.supplier_inn,
                        r.supplier_name,
                        r.search_method,
                        r.okpd2_code,
                        r.okved2_code,
                        r.user_group_id,
                        MIN(i.supply_start_date) AS supply_start_date,
                        MAX(i.supply_end_date) AS supply_end_date,
                        COUNT(DISTINCT r.item_id) AS items_count
                    FROM supplier_search_results r
                    JOIN purchase_application_items i
                        ON i.item_id = r.item_id
                    WHERE i.application_id = %s
                    GROUP BY
                        i.application_id,
                        r.supplier_id,
                        r.supplier_inn,
                        r.supplier_name,
                        r.search_method,
                        r.okpd2_code,
                        r.okved2_code,
                        r.user_group_id
                    HAVING COUNT(DISTINCT r.item_id) > 0
                    """,
                    (application_id,),
                )

                groups = cur.fetchall()

                if len(groups) == 0:
                    return {
                        "status": "NO_BATCH_GROUPS",
                        "message": "Не удалось сформировать группы для черновиков писем. Проверьте результаты подбора поставщиков.",
                        "batches": [],
                    }

                created_batches = 0

                for group in groups:
                    # Не создаем черновик, если вообще нет поставщика
                    if not group["supplier_id"] and not group["supplier_inn"] and not group["supplier_name"]:
                        continue

                    cur.execute(
                        """
                        INSERT INTO procurement_email_batches (
                            application_id,
                            supplier_id,
                            supplier_inn,
                            supplier_name,
                            search_method,
                            okpd2_code,
                            okved2_code,
                            user_group_id,
                            supply_start_date,
                            supply_end_date,
                            status
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DRAFT')
                        RETURNING batch_id
                        """,
                        (
                            group["application_id"],
                            group["supplier_id"],
                            group["supplier_inn"],
                            group["supplier_name"],
                            group["search_method"],
                            group["okpd2_code"],
                            group["okved2_code"],
                            group["user_group_id"],
                            group["supply_start_date"],
                            group["supply_end_date"],
                        ),
                    )

                    batch_id = cur.fetchone()["batch_id"]

                    cur.execute(
                        """
                        INSERT INTO procurement_email_batch_items (
                            batch_id,
                            item_id
                        )
                        SELECT DISTINCT
                            %s,
                            r.item_id
                        FROM supplier_search_results r
                        JOIN purchase_application_items i
                            ON i.item_id = r.item_id
                        WHERE i.application_id = %s
                          AND COALESCE(r.supplier_id::text, '') = COALESCE(%s::text, '')
                          AND COALESCE(r.supplier_inn, '') = COALESCE(%s, '')
                          AND COALESCE(r.supplier_name, '') = COALESCE(%s, '')
                          AND r.search_method = %s
                          AND COALESCE(r.okpd2_code, '') = COALESCE(%s, '')
                          AND COALESCE(r.okved2_code, '') = COALESCE(%s, '')
                          AND COALESCE(r.user_group_id, '') = COALESCE(%s, '')
                        """,
                        (
                            batch_id,
                            application_id,
                            group["supplier_id"],
                            group["supplier_inn"],
                            group["supplier_name"],
                            group["search_method"],
                            group["okpd2_code"],
                            group["okved2_code"],
                            group["user_group_id"],
                        ),
                    )

                    cur.execute(
                        """
                        SELECT COUNT(*) AS cnt
                        FROM procurement_email_batch_items
                        WHERE batch_id = %s
                        """,
                        (batch_id,),
                    )
                    batch_items_count = cur.fetchone()["cnt"]

                    if batch_items_count == 0:
                        cur.execute(
                            """
                            DELETE FROM procurement_email_batches
                            WHERE batch_id = %s
                            """,
                            (batch_id,),
                        )
                    else:
                        created_batches += 1

                if created_batches == 0:
                    return {
                        "status": "NO_BATCHES_CREATED",
                        "message": "Черновики писем не сформированы: нет валидных поставщиков или позиций для группировки.",
                        "batches": [],
                    }

                cur.execute(
                    """
                    UPDATE purchase_application_items
                    SET processing_status = 'EMAIL_PREPARED',
                        updated_at = now()
                    WHERE application_id = %s
                      AND item_id IN (
                          SELECT bi.item_id
                          FROM procurement_email_batch_items bi
                          JOIN procurement_email_batches b
                              ON b.batch_id = bi.batch_id
                          WHERE b.application_id = %s
                      )
                    """,
                    (application_id, application_id),
                )

        batches = get_application_batches(application_id)

        return {
            "status": "OK",
            "message": f"Черновики писем сформированы. Создано черновиков: {len(batches)}",
            "batches": batches,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка формирования черновиков писем: {str(e)}"
        )

    finally:
        conn.close()


@router.get("/application/{application_id}")
def get_application_batches(application_id: int):
    ensure_email_log_schema()
    return fetch_all("""
        SELECT
            b.*,
            s.email AS supplier_email,
            COUNT(DISTINCT bi.item_id) AS items_count,
            COUNT(DISTINCT l.log_id) FILTER (WHERE l.status = 'SENT') AS sent_logs_count,
            MAX(l.sent_at) AS last_sent_at
        FROM procurement_email_batches b
        LEFT JOIN procurement_email_batch_items bi
            ON bi.batch_id = b.batch_id
        LEFT JOIN suppliers s
            ON s.inn = b.supplier_inn
        LEFT JOIN procurement_email_logs l
            ON l.batch_id = b.batch_id
        WHERE b.application_id = %s
        GROUP BY b.batch_id, s.email
        ORDER BY
            b.search_method,
            b.supplier_name,
            b.supplier_inn
    """, (application_id,))


@router.get("/{batch_id}")
def get_batch(batch_id: int):
    ensure_email_log_schema()
    batch = fetch_one("""
        SELECT b.*, s.email AS supplier_email
        FROM procurement_email_batches b
        LEFT JOIN suppliers s ON s.inn = b.supplier_inn
        WHERE b.batch_id=%s
    """, (batch_id,))
    if not batch:
        raise HTTPException(status_code=404, detail="Черновик письма не найден")
    items = fetch_all("""
        SELECT
            a.application_no,
            a.application_date,
            a.construction_object,
            i.*
        FROM procurement_email_batch_items bi
        JOIN purchase_application_items i
            ON i.item_id = bi.item_id
        JOIN purchase_applications a
            ON a.application_id = i.application_id
        WHERE bi.batch_id = %s
        ORDER BY
            a.application_id,
            i.material_name
    """, (batch_id,))
    logs = fetch_all("""
        SELECT log_id, recipient_email, subject, status, error_message, sent_at
        FROM procurement_email_logs
        WHERE batch_id = %s
        ORDER BY sent_at DESC
    """, (batch_id,))
    subject, body = build_procurement_email(batch, items)
    return {"batch": batch, "items": items, "logs": logs, "email_preview": {"subject": subject, "body": body}}


@router.post("/send-emails")
def send_selected_emails(payload: SendEmailsRequest):
    batch_ids = list(dict.fromkeys(payload.batch_ids))
    if not batch_ids:
        raise HTTPException(status_code=400, detail="Выберите хотя бы один черновик письма для отправки")

    conn = get_connection()
    results = []

    try:
        with conn:
            with conn.cursor() as cur:
                ensure_email_log_table(cur)

        for batch_id in batch_ids:
            batch = fetch_one("""
                SELECT b.*, s.email AS supplier_email
                FROM procurement_email_batches b
                LEFT JOIN suppliers s ON s.inn = b.supplier_inn
                WHERE b.batch_id = %s
            """, (batch_id,))

            if not batch:
                results.append({"batch_id": batch_id, "status": "ERROR", "message": "Черновик не найден"})
                continue

            items = fetch_all("""
                SELECT
                    a.application_no,
                    a.application_date,
                    a.construction_object,
                    i.*
                FROM procurement_email_batch_items bi
                JOIN purchase_application_items i
                    ON i.item_id = bi.item_id
                JOIN purchase_applications a
                    ON a.application_id = i.application_id
                WHERE bi.batch_id = %s
                ORDER BY
                    a.application_id,
                    i.material_name
            """, (batch_id,))

            to_emails = extract_emails(batch.get("supplier_email"))
            subject, body = build_procurement_email(batch, items)
            status = "SENT"
            error_message = None

            try:
                send_email_smtp(to_emails, subject, body)
            except Exception as exc:
                status = "ERROR"
                error_message = str(exc)

            with get_connection() as log_conn:
                with log_conn.cursor() as cur:
                    ensure_email_log_table(cur)
                    cur.execute(
                        """
                        INSERT INTO procurement_email_logs (
                            batch_id,
                            supplier_inn,
                            supplier_name,
                            recipient_email,
                            subject,
                            body,
                            status,
                            error_message
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            batch_id,
                            batch.get("supplier_inn"),
                            batch.get("supplier_name"),
                            ", ".join(to_emails),
                            subject,
                            body,
                            status,
                            error_message,
                        ),
                    )
                    cur.execute(
                        """
                        UPDATE procurement_email_batches
                        SET status = %s, updated_at = now()
                        WHERE batch_id = %s
                        """,
                        ("SENT" if status == "SENT" else "SEND_ERROR", batch_id),
                    )
                    if status == "SENT":
                        cur.execute(
                            """
                            UPDATE purchase_application_items
                            SET processing_status = 'EMAIL_SENT', updated_at = now()
                            WHERE item_id IN (
                                SELECT item_id FROM procurement_email_batch_items WHERE batch_id = %s
                            )
                            """,
                            (batch_id,),
                        )

                    if batch.get("kp_request_id"):
                        refresh_kp_request_status(cur, batch.get("kp_request_id"))

                    log_conn.commit()

            results.append({
                "batch_id": batch_id,
                "status": status,
                "recipient_email": ", ".join(to_emails),
                "message": "Письмо отправлено" if status == "SENT" else error_message,
            })

        sent_count = sum(1 for result in results if result["status"] == "SENT")
        error_count = sum(1 for result in results if result["status"] != "SENT")
        return {
            "status": "OK" if error_count == 0 else "PARTIAL" if sent_count else "ERROR",
            "sent_count": sent_count,
            "error_count": error_count,
            "results": results,
        }

    finally:
        conn.close()


@router.get("/email-logs/recent")
def get_recent_email_logs(limit: int = 100):
    limit = max(1, min(limit, 500))
    ensure_email_log_schema()
    return fetch_all("""
        SELECT l.log_id, l.batch_id, b.application_id, b.kp_request_code, l.supplier_inn, l.supplier_name,
               l.recipient_email, l.subject, l.status, l.error_message, l.sent_at
        FROM procurement_email_logs l
        LEFT JOIN procurement_email_batches b ON b.batch_id = l.batch_id
        ORDER BY l.sent_at DESC
        LIMIT %s
    """, (limit,))

@router.get("")
def get_all_batches(limit: int = 500):
    ensure_email_log_schema()
    limit = max(1, min(limit, 2000))

    return fetch_all(
        """
        SELECT
            b.*,
            s.email AS supplier_email,
            COUNT(DISTINCT bi.item_id) AS items_count,
            COUNT(DISTINCT i.application_id) AS applications_count,
            COUNT(DISTINCT l.log_id) FILTER (WHERE l.status = 'SENT') AS sent_logs_count,
            MAX(l.sent_at) AS last_sent_at
        FROM procurement_email_batches b
        LEFT JOIN procurement_email_batch_items bi
            ON bi.batch_id = b.batch_id
        LEFT JOIN purchase_application_items i
            ON i.item_id = bi.item_id
        LEFT JOIN suppliers s
            ON s.inn = b.supplier_inn
        LEFT JOIN procurement_email_logs l
            ON l.batch_id = b.batch_id
        GROUP BY b.batch_id, s.email
        ORDER BY
            b.created_at DESC,
            b.search_method,
            b.supplier_name,
            b.supplier_inn
        LIMIT %s
        """,
        (limit,),
    )