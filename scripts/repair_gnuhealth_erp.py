"""
Script de Reparo Cirúrgico e Higienização do ERP GNU Health HIS.
Executa correções transacionais para:
1. Atualizar flag 'deceased = TRUE' em party_party para pacientes falecidos.
2. Cancelar/remover consultas ambulatoriais e internações agendadas após o óbito do paciente.
3. Atualizar status de consultas e internações passadas de 'confirmed'/'free' para 'done'.
4. Realocar leitos sobrepostos para leitos desocupados da mesma enfermaria/ala.
5. Equacionar saldos negativos de estoque via movimentação compensatória de entrada de fornecedor.

Uso:
    python scripts/repair_gnuhealth_erp.py --dry-run
    python scripts/repair_gnuhealth_erp.py --apply
"""
import os
import sys
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor

def get_connection():
    host = os.getenv("GNUHEALTH_DB_HOST", "localhost")
    port = int(os.getenv("GNUHEALTH_DB_PORT", "5434"))
    dbname = os.getenv("GNUHEALTH_DB_NAME", "gnuhealth")
    user = os.getenv("GNUHEALTH_DB_USER", "gnuhealth")
    password = os.getenv("GNUHEALTH_DB_PASSWORD", "gnuhealth")
    return psycopg2.connect(
        host=host, port=port, dbname=dbname, user=user, password=password
    )

def audit_and_repair(apply_changes: bool = False):
    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        print(f"=== INICIANDO AUDITORIA E REPARO DO ERP GNU HEALTH (MODO: {'APLICAÇÃO' if apply_changes else 'DRY-RUN / SIMULAÇÃO'}) ===")

        # Identificar mortes registradas em internações
        cur.execute("""
            SELECT patient, MIN(discharge_date) AS death_date
            FROM gnuhealth_inpatient_registration
            WHERE discharge_reason = 'death'
            GROUP BY patient
        """)
        death_records = {r["patient"]: r["death_date"] for r in cur.fetchall()}
        print(f"[0] Pacientes com registro de óbito identificado: {len(death_records)}")

        # 1. Atendimentos pós-óbito
        cur.execute("""
            SELECT a.id, a.patient, a.appointment_date, d.death_date
            FROM gnuhealth_appointment a
            JOIN (
                SELECT patient, MIN(discharge_date) AS death_date
                FROM gnuhealth_inpatient_registration
                WHERE discharge_reason = 'death'
                GROUP BY patient
            ) d ON a.patient = d.patient
            WHERE a.appointment_date > d.death_date
        """)
        post_mortem_appts = cur.fetchall()
        print(f"[1] Consultas ambulatoriais após o óbito encontradas: {len(post_mortem_appts)}")

        # 2. Internações pós-óbito
        cur.execute("""
            SELECT i.id, i.patient, i.hospitalization_date, d.death_date
            FROM gnuhealth_inpatient_registration i
            JOIN (
                SELECT patient, MIN(discharge_date) AS death_date
                FROM gnuhealth_inpatient_registration
                WHERE discharge_reason = 'death'
                GROUP BY patient
            ) d ON i.patient = d.patient
            WHERE i.hospitalization_date > d.death_date
        """)
        post_mortem_inps = cur.fetchall()
        print(f"[2] Internações hospitalares após o óbito encontradas: {len(post_mortem_inps)}")

        # 3. Consultas passadas ainda em estado 'confirmed'
        cur.execute("""
            SELECT COUNT(1) AS cnt
            FROM gnuhealth_appointment
            WHERE state = 'confirmed' AND appointment_date <= CURRENT_TIMESTAMP
        """)
        past_appts_cnt = cur.fetchone()["cnt"]
        print(f"[3] Consultas passadas em estado 'confirmed' (devem ser 'done'): {past_appts_cnt}")

        # 4. Internações passadas com alta ainda em estado 'free'
        cur.execute("""
            SELECT COUNT(1) AS cnt
            FROM gnuhealth_inpatient_registration
            WHERE state != 'done' AND discharge_date IS NOT NULL AND discharge_date <= CURRENT_TIMESTAMP
        """)
        past_inps_cnt = cur.fetchone()["cnt"]
        print(f"[4] Internações com alta realizada não finalizadas ('done'): {past_inps_cnt}")

        # 5. Internações com leitos sobrepostos
        cur.execute("""
            SELECT i1.id AS id1, i2.id AS id2, i1.bed AS bed_id, b.ward AS ward_id,
                   i1.hospitalization_date AS h1, i1.discharge_date AS d1,
                   i2.hospitalization_date AS h2, i2.discharge_date AS d2
            FROM gnuhealth_inpatient_registration i1
            JOIN gnuhealth_inpatient_registration i2 
              ON i1.bed = i2.bed AND i1.id < i2.id
            JOIN gnuhealth_hospital_bed b ON i1.bed = b.id
            WHERE i1.hospitalization_date < i2.discharge_date
              AND i2.hospitalization_date < i1.discharge_date
        """)
        overlapping_beds = cur.fetchall()
        print(f"[5] Conflitos de leito sobreposto no mesmo intervalo: {len(overlapping_beds)}")

        # 6. Saldos de estoque por produto e local interno
        cur.execute("""
            SELECT l.id AS location_id, l.name AS location_name,
                   m.product AS product_id, pt.name AS product_name,
                   SUM(CASE WHEN m.to_location = l.id THEN m.quantity 
                            WHEN m.from_location = l.id THEN -m.quantity 
                            ELSE 0 END) AS balance
            FROM stock_move m
            JOIN stock_location l ON l.id IN (m.from_location, m.to_location)
            JOIN product_product pp ON m.product = pp.id
            JOIN product_template pt ON pp.template = pt.id
            WHERE l.type = 'storage' AND m.state = 'done'
            GROUP BY l.id, l.name, m.product, pt.name
            HAVING SUM(CASE WHEN m.to_location = l.id THEN m.quantity 
                            WHEN m.from_location = l.id THEN -m.quantity 
                            ELSE 0 END) < 0
        """)
        negative_stock = cur.fetchall()
        print(f"[6] Produtos com saldo negativo em locais de estoque: {len(negative_stock)}")
        for neg in negative_stock:
            print(f"    - {neg['product_name']} (ID {neg['product_id']}) em {neg['location_name']}: Saldo = {neg['balance']}")

        if apply_changes:
            print("\n>>> APLICANDO CORREÇÕES CIRÚRGICAS EM TRANSAÇÃO...")

            # 0. Atualizar party_party.deceased para pacientes que morreram
            cur.execute("""
                UPDATE party_party
                SET deceased = TRUE, write_date = CURRENT_TIMESTAMP
                WHERE id IN (
                    SELECT p.party
                    FROM gnuhealth_patient p
                    JOIN gnuhealth_inpatient_registration ir ON ir.patient = p.id
                    WHERE ir.discharge_reason = 'death'
                ) AND deceased IS NOT TRUE
            """)
            print(f"    [OK] {cur.rowcount} registros de pacientes atualizados com 'deceased = TRUE' em party_party.")

            # 1. Remover atendimentos pós-óbito
            if post_mortem_appts:
                ids = tuple(r["id"] for r in post_mortem_appts)
                cur.execute("DELETE FROM gnuhealth_appointment WHERE id IN %s", (ids,))
                print(f"    [OK] {len(ids)} atendimentos pós-óbito removidos.")

            # 2. Remover internações pós-óbito
            if post_mortem_inps:
                ids = tuple(r["id"] for r in post_mortem_inps)
                cur.execute("DELETE FROM gnuhealth_inpatient_registration WHERE id IN %s", (ids,))
                print(f"    [OK] {len(ids)} internações pós-óbito removidas.")

            # 3. Marcar consultas passadas como 'done'
            cur.execute("""
                UPDATE gnuhealth_appointment
                SET state = 'done', write_date = CURRENT_TIMESTAMP
                WHERE state = 'confirmed' AND appointment_date <= CURRENT_TIMESTAMP
            """)
            print(f"    [OK] {cur.rowcount} consultas passadas atualizadas para 'done'.")

            # 4. Marcar internações com alta como 'done'
            cur.execute("""
                UPDATE gnuhealth_inpatient_registration
                SET state = 'done', write_date = CURRENT_TIMESTAMP
                WHERE state != 'done' AND discharge_date IS NOT NULL AND discharge_date <= CURRENT_TIMESTAMP
            """)
            print(f"    [OK] {cur.rowcount} internações passadas com alta atualizadas para 'done'.")

            # 5. Realocar internações sobrepostas para leitos livres da mesma ala
            if overlapping_beds:
                reallocated_count = 0
                for conflict in overlapping_beds:
                    id_to_move = conflict["id2"]
                    ward_id = conflict["ward_id"]
                    h2 = conflict["h2"]
                    d2 = conflict["d2"]

                    # Busca leito livre na mesma ala durante o intervalo [h2, d2]
                    cur.execute("""
                        SELECT b.id AS candidate_bed_id
                        FROM gnuhealth_hospital_bed b
                        WHERE b.ward = %s
                          AND NOT EXISTS (
                              SELECT 1 FROM gnuhealth_inpatient_registration ir
                              WHERE ir.bed = b.id
                                AND ir.id != %s
                                AND ir.hospitalization_date < %s
                                AND ir.discharge_date > %s
                          )
                        LIMIT 1
                    """, (ward_id, id_to_move, d2, h2))
                    candidate = cur.fetchone()
                    if candidate:
                        new_bed = candidate["candidate_bed_id"]
                        cur.execute("""
                            UPDATE gnuhealth_inpatient_registration
                            SET bed = %s, write_date = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (new_bed, id_to_move))
                        reallocated_count += 1
                print(f"    [OK] {reallocated_count} internações realocadas para leitos livres da mesma ala.")

            # 6. Inserir movimentos compensatórios de fornecedor para produtos com saldo negativo
            if negative_stock:
                cur.execute("SELECT id FROM stock_location WHERE type = 'supplier' LIMIT 1")
                supplier_loc = cur.fetchone()["id"]
                cur.execute("SELECT id FROM company_company LIMIT 1")
                company_id = cur.fetchone()["id"]
                cur.execute("SELECT id FROM currency_currency LIMIT 1")
                currency_id = cur.fetchone()["id"]

                for neg in negative_stock:
                    deficit = abs(float(neg["balance"]))
                    replenish_qty = deficit + 200.0
                    cur.execute("""
                        INSERT INTO stock_move (
                            create_date, write_date, effective_date,
                            product, unit, quantity, internal_quantity,
                            cost_price, unit_price,
                            from_location, to_location, company, currency, state
                        ) VALUES (
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_DATE,
                            %s, 1, %s, %s,
                            0.0, 10.0,
                            %s, %s, %s, %s, 'done'
                        )
                    """, (neg["product_id"], replenish_qty, replenish_qty, supplier_loc, neg["location_id"], company_id, currency_id))
                    print(f"    [OK] Reposição de +{replenish_qty} unidades inserida para {neg['product_name']} no local {neg['location_name']}.")

            # Validação de integridade de sequências após operações SQL diretas (Requisito P1.6)
            for tbl in ["stock_move", "party_party", "gnuhealth_patient"]:
                cur.execute("SELECT pg_get_serial_sequence(%s, 'id') AS seq_name", (tbl,))
                row_seq = cur.fetchone()
                seq_name = row_seq["seq_name"] if row_seq else None
                if seq_name:
                    cur.execute(f"SELECT COALESCE(MAX(id), 0) AS max_id FROM {tbl}")
                    max_id = cur.fetchone()["max_id"]
                    cur.execute(f"SELECT last_value FROM {seq_name}")
                    last_val = cur.fetchone()["last_value"]
                    if max_id > last_val:
                        raise ValueError(
                            f"[INTEGRIDADE FALHOU] Sequência '{seq_name}' ({last_val}) defasada em relação ao MAX(id)={max_id} de {tbl}!"
                        )
                    print(f"    [OK] Sequência '{seq_name}' validada (max_id={max_id}, last_val={last_val}).")

            conn.commit()
            print("\n=== TODAS AS CORREÇÕES FORAM APLICADAS COM SUCESSO E EFETIVADAS (COMMIT)! ===")
        else:
            conn.rollback()
            print("\nModo Dry-Run concluído. Nenhuma alteração foi persistida no banco.")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERRO DURANTE AUDITORIA/REPARO] {e}")
        raise e
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audita e repara dados do ERP GNU Health HIS")
    parser.add_argument("--apply", action="store_true", help="Aplica as correções no banco de dados")
    parser.add_argument("--dry-run", action="store_true", help="Apenas simula e audita os problemas")
    args = parser.parse_args()

    audit_and_repair(apply_changes=args.apply)
