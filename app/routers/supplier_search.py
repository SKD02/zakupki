from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.database import get_connection, fetch_all

router = APIRouter()


SEARCH_METHOD_OKPD_SPARK = "OKPD_OKVED_SPARK"
SEARCH_METHOD_GROUP_AI = "MATERIAL_GROUP_AI"

ALLOWED_SEARCH_METHODS = {
    SEARCH_METHOD_OKPD_SPARK,
    SEARCH_METHOD_GROUP_AI,
}


class SupplierSearchRequest(BaseModel):
    methods: list[str] = Field(
        default_factory=lambda: [
            SEARCH_METHOD_OKPD_SPARK,
            SEARCH_METHOD_GROUP_AI,
        ]
    )


@router.post("/application/{application_id}/run")
def run_supplier_search(application_id: int, payload: SupplierSearchRequest):
    conn = get_connection()

    methods = payload.methods if payload else [
        SEARCH_METHOD_OKPD_SPARK,
        SEARCH_METHOD_GROUP_AI,
    ]

    methods = list(dict.fromkeys(methods))

    invalid_methods = [
        method for method in methods
        if method not in ALLOWED_SEARCH_METHODS
    ]

    if invalid_methods:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Переданы неизвестные методы подбора поставщиков",
                "invalid_methods": invalid_methods,
                "allowed_methods": list(ALLOWED_SEARCH_METHODS),
            },
        )

    if not methods:
        raise HTTPException(
            status_code=400,
            detail="Не выбран ни один метод подбора поставщиков"
        )

    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Проверяем, есть ли позиции заявки для поиска
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM purchase_application_items
                    WHERE application_id = %s
                      AND add_to_search = true
                    """,
                    (application_id,),
                )

                items_count = cur.fetchone()["cnt"]

                if items_count == 0:
                    return {
                        "status": "NO_ITEMS",
                        "message": "В заявке нет позиций для подбора поставщиков",
                        "selected_methods": methods,
                        "results": [],
                    }

                # 2. Очищаем старые результаты по этой заявке
                cur.execute(
                    """
                    DELETE FROM supplier_search_results
                    WHERE item_id IN (
                        SELECT item_id
                        FROM purchase_application_items
                        WHERE application_id = %s
                    )
                    """,
                    (application_id,),
                )

                # 3. Метод 1:
                # Material → OKPD2 → OKVED2 → suppliers / SPARK
                if SEARCH_METHOD_OKPD_SPARK in methods:
                    cur.execute(
                        """
                        INSERT INTO supplier_search_results (
                            item_id,
                            supplier_id,
                            search_method,
                            source_system,
                            material_id,
                            okpd2_code,
                            okved2_code,
                            user_group_id,
                            supplier_inn,
                            supplier_name,
                            match_reason
                        )
                        SELECT DISTINCT
                            i.item_id,
                            sr.supplier_id AS supplier_id,
                            %s AS search_method,
                            'SPARK' AS source_system,
                            trim(i.material_id) AS material_id,
                            trim(mom.okpd2_code) AS okpd2_code,
                            trim(oom.okved2_code) AS okved2_code,
                            NULL::text AS user_group_id,
                            trim(sr.inn) AS supplier_inn,
                            sr.name AS supplier_name,
                            'Материал найден через Material → OKPD2 → OKVED2 → suppliers / SPARK'
                        FROM purchase_application_items i
                        JOIN material_okpd2_map mom
                            ON trim(mom.material_id) = trim(i.material_id)
                        JOIN okpd2_okved2_map oom
                            ON trim(oom.okpd2_code) = trim(mom.okpd2_code)
                        JOIN suppliers sr
                            ON trim(sr.okved2_code) = trim(oom.okved2_code)
                        WHERE i.application_id = %s
                          AND i.add_to_search = true
                          AND i.material_id IS NOT NULL
                          AND trim(i.material_id) <> ''
                          AND sr.inn IS NOT NULL
                          AND trim(sr.inn) <> ''
                        """,
                        (
                            SEARCH_METHOD_OKPD_SPARK,
                            application_id,
                        ),
                    )
                # 4. Метод 2:
                # Material → Group → user_group_supply_map / suppliers
                if SEARCH_METHOD_GROUP_AI in methods:
                    cur.execute(
                        """
                        INSERT INTO supplier_search_results (
                            item_id,
                            supplier_id,
                            search_method,
                            source_system,
                            material_id,
                            okpd2_code,
                            okved2_code,
                            user_group_id,
                            supplier_inn,
                            supplier_name,
                            match_reason
                        )
                        SELECT DISTINCT
                            i.item_id,
                            ai.supplier_id AS supplier_id,
                            %s AS search_method,
                            'AI' AS source_system,
                            i.material_id,
                            NULL::text AS okpd2_code,
                            NULL::text AS okved2_code,
                            mugm.id_possition AS user_group_id,
                            ugsm.inn_supply AS supplier_inn,
                            COALESCE(
                                NULLIF(ai.name, ''),
                                ugsm.inn_supply
                            ) AS supplier_name,
                            'Материал найден через Material → Group → user_group_supply_map / suppliers'
                        FROM purchase_application_items i
                        JOIN material_user_group_map mugm
                            ON mugm.material_id = i.material_id
                        JOIN user_group_supply_map ugsm
                            ON ugsm.user_group_id = mugm.id_possition
                        LEFT JOIN suppliers ai
                            ON ai.inn = ugsm.inn_supply
                        WHERE i.application_id = %s
                          AND i.add_to_search = true
                          AND ugsm.inn_supply IS NOT NULL
                          AND trim(ugsm.inn_supply) <> ''
                        """,
                        (
                            SEARCH_METHOD_GROUP_AI,
                            application_id,
                        ),
                    )

                # 5. Проверяем, появились ли результаты
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

                results_count = cur.fetchone()["cnt"]

                if results_count == 0:
                    cur.execute(
                        """
                        UPDATE purchase_application_items
                        SET processing_status = 'NO_SUPPLIERS',
                            updated_at = now()
                        WHERE application_id = %s
                          AND add_to_search = true
                        """,
                        (application_id,),
                    )

                    return {
                        "status": "NO_SUPPLIERS",
                        "message": build_no_suppliers_message(methods),
                        "selected_methods": methods,
                        "results": [],
                    }

                # 6. Обновляем статусы найденных позиций
                cur.execute(
                    """
                    UPDATE purchase_application_items i
                    SET processing_status = 'SUPPLIERS_FOUND',
                        updated_at = now()
                    WHERE i.application_id = %s
                      AND EXISTS (
                          SELECT 1
                          FROM supplier_search_results r
                          WHERE r.item_id = i.item_id
                      )
                    """,
                    (application_id,),
                )

                # 7. Обновляем статусы ненайденных позиций
                cur.execute(
                    """
                    UPDATE purchase_application_items i
                    SET processing_status = 'NO_SUPPLIERS',
                        updated_at = now()
                    WHERE i.application_id = %s
                      AND i.add_to_search = true
                      AND NOT EXISTS (
                          SELECT 1
                          FROM supplier_search_results r
                          WHERE r.item_id = i.item_id
                      )
                    """,
                    (application_id,),
                )

        results = get_supplier_search_results(application_id)

        return {
            "status": "OK",
            "message": f"Подбор поставщиков выполнен. Найдено записей: {len(results)}",
            "selected_methods": methods,
            "results": results,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка подбора поставщиков: {str(e)}"
        )

    finally:
        conn.close()


@router.get("/application/{application_id}/results")
def get_supplier_search_results(application_id: int):
    return fetch_all(
        """
        SELECT
            r.search_result_id,
            r.item_id,
            r.supplier_id,
            r.search_method,
            r.source_system,
            r.material_id,
            r.okpd2_code,
            r.okved2_code,
            r.user_group_id,
            r.supplier_inn,
            r.supplier_name,
            r.match_reason,
            r.is_selected,
            r.created_at,
            i.material_name,
            i.unit,
            i.quantity,
            i.work_doc_code,
            i.supply_start_date,
            i.supply_end_date
        FROM supplier_search_results r
        JOIN purchase_application_items i
            ON i.item_id = r.item_id
        WHERE i.application_id = %s
        ORDER BY
            r.search_method,
            r.source_system,
            r.supplier_name,
            i.material_name
        """,
        (application_id,),
    )


def build_no_suppliers_message(methods: list[str]) -> str:
    checks = []

    if SEARCH_METHOD_OKPD_SPARK in methods:
        checks.append(
            "для SPARK-подбора проверьте связки Material→OKPD2, OKPD2→OKVED2 и наличие поставщиков в suppliers по okved2_code"
        )

    if SEARCH_METHOD_GROUP_AI in methods:
        checks.append(
            "для AI-подбора проверьте связки Material→Group и Group→Supplier в user_group_supply_map"
        )

    if not checks:
        return "Поставщики не найдены."

    return "Поставщики не найдены: " + "; ".join(checks) + "."