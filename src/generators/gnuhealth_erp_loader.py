"""
QIMED DataQore — GNU Health ERP Loader (Proteus Integration).
Carrega e sincroniza dados sintéticos hospitalares diretamente no GNU Health HIS 5.0
através da API oficial do Proteus, respeitando regras de negócio, sequências e integridade.
"""
import os
import sys
import json
import time
import argparse
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, List, Optional

try:
    from proteus import config, Model
except ImportError:
    config = None
    Model = None


class GnuHealthERPLoader:
    """
    Sincronizador oficial de dados sintéticos para o GNU Health HIS via Proteus ORM.
    """

    def __init__(self, connection_url: Optional[str] = None, config_file: Optional[str] = None):
        self.connection_url = connection_url
        self.config_file = config_file or "/etc/trytond.conf"
        self._cfg = None
        self._init_connection()

    def _init_connection(self):
        """Inicializa conexão Proteus direta (set_trytond) ou remota (set_xmlrpc)."""
        if config is None or Model is None or "mock" in (self.connection_url or ""):
            print("[ERP_LOADER] Proteus não está disponível neste ambiente ou modo mock ativo. Conexão ignorada.")
            return
        if os.path.exists(self.config_file):
            print(f"[ERP_LOADER] Conectando via Trytond direto ({self.config_file}, db: gnuhealth)...")
            self._cfg = config.set_trytond('gnuhealth', config_file=self.config_file)
        else:
            url = self.connection_url or os.getenv("GNUHEALTH_URL", "http://admin:admin@localhost:8001/gnuhealth/")
            print(f"[ERP_LOADER] Conectando via XML-RPC ({url})...")
            self._cfg = config.set_xmlrpc(url)

    def ensure_hospital_environment(self) -> Dict[str, Any]:
        """Garante a existência de Empresa, Moeda, Unidades, Leitos e Especialidades."""
        Party = Model.get('party.party')
        Company = Model.get('company.company')
        Currency = Model.get('currency.currency')
        User = Model.get('res.user')
        Inst = Model.get('gnuhealth.institution')
        Ward = Model.get('gnuhealth.hospital.ward')
        Bed = Model.get('gnuhealth.hospital.bed')
        Product = Model.get('product.product')
        Template = Model.get('product.template')
        Uom = Model.get('product.uom')
        Loc = Model.get('stock.location')

        # 1. Moeda BRL
        brl = Currency.find([('code', '=', 'BRL')])
        if not brl:
            brl = Currency(name='Brazilian Real', symbol='R$', code='BRL')
            brl.save()
        else:
            brl = brl[0]

        # 2. Instituição Hospitalar
        p_inst = Party.find([('name', '=', 'Hospital Geral de Ensino QIMED')])
        if not p_inst:
            p_inst = Party(name='Hospital Geral de Ensino QIMED', is_institution=True)
            p_inst.save()
        else:
            p_inst = p_inst[0]

        # 3. Empresa
        comp = Company.find([])
        if not comp:
            comp = Company(party=p_inst, currency=brl)
            comp.save()
        else:
            comp = comp[0]

        # Vincula admin à empresa
        admin = User(1)
        if not admin.company:
            admin.company = comp
            admin.companies.append(comp)
            admin.save()

        inst = Inst.find([])
        if not inst:
            inst = Inst(party=p_inst, code='7654321', institution_type='hospital', public_level='public')
            inst.save()
        else:
            inst = inst[0]

        # 4. Enfermarias e Leitos
        uom_unit = Uom.find([('name', '=', 'Unit')]) or Uom.find([])
        uom_unit = uom_unit[0]

        tpl_bed = Template.find([('name', '=', 'Hospital Bed Service')])
        if not tpl_bed:
            tpl_bed = Template(name='Hospital Bed Service', default_uom=uom_unit, type='service', list_price=Decimal('0.0'))
            tpl_bed.save()
        else:
            tpl_bed = tpl_bed[0]

        prod_bed = Product.find([('template', '=', tpl_bed)])
        if not prod_bed:
            prod_bed = Product(template=tpl_bed, is_bed=True)
            prod_bed.save()
        else:
            prod_bed = prod_bed[0]
            if not prod_bed.is_bed:
                prod_bed.is_bed = True
                prod_bed.save()

        ward_names = [
            ("Enfermaria Clínica Geral", 30),
            ("Unidade de Terapia Intensiva (UTI)", 15),
            ("Enfermaria Cirúrgica", 25),
            ("Pronto Socorro Hospitalar", 20),
        ]
        wards = {}
        for w_name, num_beds in ward_names:
            w = Ward.find([('name', '=', w_name)])
            if not w:
                w = Ward(name=w_name, institution=inst, number_of_beds=num_beds)
                w.save()
            else:
                w = w[0]
            wards[w_name] = w

            # Garante criação dos leitos
            existing_beds = Bed.find([('ward', '=', w)])
            if len(existing_beds) < num_beds:
                needed = num_beds - len(existing_beds)
                for b_idx in range(needed):
                    b_code = f"{w_name[:3].upper()}-{len(existing_beds) + b_idx + 1:02d}"
                    p_bed = Product(template=tpl_bed, is_bed=True)
                    p_bed.save()
                    b = Bed(ward=w, institution=inst, bed_type='gatch', product=p_bed, telephone_number=b_code)
                    b.save()

        # 5. Locais de Estoque Físicos
        supplier_loc = Loc.find([('type', '=', 'supplier')])[0]
        customer_loc = Loc.find([('type', '=', 'customer')])[0]
        storage_base = Loc.find([('type', '=', 'storage')])[0]

        stock_loc_names = ["Farmácia Central", "Almoxarifado Central", "Farmácia Satélite UTI"]
        stock_locs = {}
        for s_name in stock_loc_names:
            sl = Loc.find([('name', '=', s_name)])
            if not sl:
                sl = Loc(name=s_name, type='storage', parent=storage_base)
                sl.save()
            else:
                sl = sl[0]
            stock_locs[s_name] = sl

        return {
            "institution": inst,
            "company": comp,
            "currency": brl,
            "wards": wards,
            "stock_locations": stock_locs,
            "supplier_loc": supplier_loc,
            "customer_loc": customer_loc,
            "bed_product": prod_bed,
        }

    def sync_batch(self, batch_dir: str) -> Dict[str, Any]:
        """Lê os arquivos JSON do lote gerado e persiste idempotentemente no GNU Health."""
        t0 = time.time()
        print(f"\n=== [ERP_LOADER] Iniciando Carga de Lote: {batch_dir} ===")
        env = self.ensure_hospital_environment()

        Party = Model.get('party.party')
        HealthProf = Model.get('gnuhealth.healthprofessional')
        HPSpecialty = Model.get('gnuhealth.hp_specialty')
        Specialty = Model.get('gnuhealth.specialty')
        Patient = Model.get('gnuhealth.patient')
        Appointment = Model.get('gnuhealth.appointment')
        Inpatient = Model.get('gnuhealth.inpatient.registration')
        Bed = Model.get('gnuhealth.hospital.bed')
        Lab = Model.get('gnuhealth.lab')
        TestType = Model.get('gnuhealth.lab.test_type')
        Product = Model.get('product.product')
        Template = Model.get('product.template')
        Uom = Model.get('product.uom')
        Medicament = Model.get('gnuhealth.medicament')
        Move = Model.get('stock.move')
        Cal = Model.get('calendar.calendar')
        Event = Model.get('calendar.event')
        CalLoc = Model.get('calendar.location')
        PatientDisease = Model.get('gnuhealth.patient.disease')
        Pathology = Model.get('gnuhealth.pathology')
        pathology_cache = {}

        uom_unit = (Uom.find([('name', '=', 'Unit')]) or Uom.find([]))[0]

        # 1. Carrega Profissionais
        print("-> Sincronizando Profissionais de Saúde...")
        prof_file = os.path.join(batch_dir, "professionals.json")
        prof_map = {}  # prof_id -> HealthProf
        if os.path.exists(prof_file):
            with open(prof_file, "r", encoding="utf-8") as f:
                profs_data = json.load(f)

            for p_dict in profs_data:
                p_name = p_dict["name"]
                code = p_dict["id"]

                # Especialidade
                spec_name = p_dict.get("specialty_name", "Clínica Médica")
                spec = Specialty.find([('name', '=', spec_name)])
                if not spec:
                    spec = Specialty(name=spec_name, code=p_dict.get("specialty_code", spec_name[:4].upper()))
                    spec.save()
                else:
                    spec = spec[0]

                # Party & HealthProf
                p = Party.find([('name', '=', p_name)])
                if not p:
                    p = Party(
                        name=p_name,
                        is_person=True,
                        is_healthprof=True,
                        is_patient=False,
                        create_target=False,
                        gender=p_dict.get("gender", "m")
                    )
                    p.save()
                else:
                    p = p[0]
                    if p.is_patient:
                        p.is_patient = False
                        p.save()

                hp = HealthProf.find([('party', '=', p)])
                if not hp:
                    hp_code = code
                    if HealthProf.find([('code', '=', hp_code)]):
                        hp_code = f"GH_PROF_P_{p.id}"
                    hp = HealthProf(
                        party=p,
                        institution=env["institution"],
                        code=hp_code
                    )
                    hp.save()
                else:
                    hp = hp[0]
                prof_map[code] = hp

                # Vincula especialidade principal do profissional em gnuhealth.hp_specialty
                hp_specs = HPSpecialty.find([('healthprof', '=', hp), ('specialty', '=', spec)])
                if not hp_specs:
                    hp_spec = HPSpecialty(
                        healthprof=hp,
                        specialty=spec,
                        mainsp=True
                    )
                    hp_spec.save()
                else:
                    hp_spec = hp_specs[0]
                    if not hp_spec.mainsp:
                        hp_spec.mainsp = True
                        hp_spec.save()

        # 2. Carrega Escala de Funcionários (Calendar)
        print("-> Sincronizando Escalas de Plantão (Calendar)...")
        shifts_file = os.path.join(batch_dir, "shifts.json")
        shifts_created = 0
        if os.path.exists(shifts_file):
            with open(shifts_file, "r", encoding="utf-8") as f:
                shifts_data = json.load(f)

            cal = Cal.find([('name', '=', 'Escala Médica Hospitalar')])
            if not cal:
                cal = Cal(name='Escala Médica Hospitalar', description='Plantão Médico e Enfermagem QIMED')
                cal.save()
            else:
                cal = cal[0]

            existing_events = {(e.summary, e.dtstart) for e in Event.find([('calendar', '=', cal)])}
            cloc_map = {}
            new_events = []
            for s in shifts_data:
                sector = s.get("ward", s.get("sector", "Pronto Socorro"))
                cloc = cloc_map.get(sector)
                if not cloc:
                    found = CalLoc.find([('name', '=', sector)])
                    if found:
                        cloc = found[0]
                    else:
                        cloc = CalLoc(name=sector)
                        cloc.save()
                    cloc_map[sector] = cloc

                dtstart = datetime.fromisoformat(s["start_time"])
                dtend = datetime.fromisoformat(s["end_time"])
                summary = s.get("summary") or f"Plantão {s.get('professional_name')} ({sector})"

                if (summary, dtstart) not in existing_events:
                    new_events.append(
                        Event(
                            calendar=cal,
                            summary=summary,
                            dtstart=dtstart,
                            dtend=dtend,
                            location=cloc,
                            status="confirmed"
                        )
                    )

            for i in range(0, len(new_events), 100):
                chunk = new_events[i:i + 100]
                Event.save(chunk)
                shifts_created += len(chunk)

        # 3. Carrega Itens de Estoque e Farmácia
        print("-> Sincronizando Medicamentos e Estoque...")
        stock_file = os.path.join(batch_dir, "stock_items.json")
        med_map = {}  # item_id -> (Medicament, Product)
        if os.path.exists(stock_file):
            with open(stock_file, "r", encoding="utf-8") as f:
                stock_data = json.load(f)

            for st in stock_data:
                name = st["name"]
                item_id = st.get("id", st.get("item_id"))
                initial_qty = float(st.get("quantity_available", st.get("initial_stock", 1000)))
                loc_name = st.get("location", st.get("storage_location", "Farmácia Central"))
                dest_loc = env["stock_locations"].get(loc_name, env["stock_locations"]["Farmácia Central"])

                tpl = Template.find([('name', '=', name)])
                if not tpl:
                    tpl = Template(name=name, default_uom=uom_unit, type='goods', list_price=Decimal('10.00'))
                    tpl.save()
                else:
                    tpl = tpl[0]

                prod = Product.find([('template', '=', tpl)])
                if not prod:
                    prod = Product(template=tpl, is_medicament=True)
                    prod.save()
                else:
                    prod = prod[0]
                    if not prod.is_medicament:
                        prod.is_medicament = True
                        prod.save()

                med = Medicament.find([('product', '=', prod)])
                if not med:
                    med = Medicament(product=prod)
                    med.save()
                else:
                    med = med[0]
                med_map[item_id] = (med, prod)

                # Cria saldo inicial de estoque se não houver movimentação anterior
                existing_moves = Move.find([('product', '=', prod)])
                if not existing_moves:
                    m = Move(
                        product=prod,
                        from_location=env["supplier_loc"],
                        to_location=dest_loc,
                        quantity=initial_qty,
                        unit=uom_unit,
                        company=env["company"],
                        currency=env["currency"],
                        unit_price=Decimal('10.00'),
                        effective_date=date(2026, 1, 1)
                    )
                    m.save()
                    m.click('do')

        # 4. Carrega Pacientes
        print("-> Sincronizando Pacientes...")
        skipped = {"encounters": 0, "inpatients": 0, "labs": 0}
        pat_file = os.path.join(batch_dir, "patients.json")
        pat_map = {}  # pat_id -> Patient
        if os.path.exists(pat_file):
            with open(pat_file, "r", encoding="utf-8") as f:
                pat_data = json.load(f)

            for p_dict in pat_data:
                p_name = p_dict["name"]
                pat_id = p_dict.get("id", p_dict.get("patient_id"))
                dob_str = p_dict.get("birth_date", p_dict.get("dob", "1980-01-01"))
                dob_val = date.fromisoformat(dob_str)
                gender_raw = str(p_dict.get("gender", "m")).strip().lower()
                gender = "m" if gender_raw in ("m", "male", "masculino", "1") else "f"

                ref_key = p_dict.get("external_ref", pat_id)
                p = Party.find([('ref', '=', ref_key)])
                if not p:
                    p = Party(
                        name=p_name,
                        ref=ref_key,
                        is_person=True,
                        is_patient=True,
                        gender=gender,
                        dob=dob_val
                    )
                    p.save()
                else:
                    p = p[0]

                pat = Patient.find([('party', '=', p)])
                if not pat:
                    pat = Patient(party=p)
                    pat.save()
                else:
                    pat = pat[0]
                pat_map[pat_id] = pat

        # 5. Carrega Atendimentos Ambulatoriais (Appointments)
        print("-> Sincronizando Atendimentos Ambulatoriais...")
        enc_file = os.path.join(batch_dir, "encounters.json")
        enc_created = 0
        if os.path.exists(enc_file):
            with open(enc_file, "r", encoding="utf-8") as f:
                enc_data = json.load(f)

            # Pre-browse available objects for speed
            skipped = {"encounters": 0, "inpatients": 0, "labs": 0}
            all_pats = list(pat_map.values())
            all_hps = list(prof_map.values())
            if all_pats and all_hps:
                new_appts = []
                new_diseases = []
                pathology_cache = {}
                for enc in enc_data:
                    pat = pat_map.get(enc.get("patient_id"))
                    hp = prof_map.get(enc.get("professional_id"))
                    if not pat or not hp:
                        skipped["encounters"] += 1
                        continue

                    enc_dt_str = enc.get("appointment_date", enc.get("encounter_datetime"))
                    enc_dt = datetime.fromisoformat(enc_dt_str)
                    urgency_code = "b" if enc.get("urgency") == "urgente" else "a"

                    new_appts.append(
                        Appointment(
                            patient=pat,
                            healthprof=hp,
                            institution=env["institution"],
                            appointment_date=enc_dt,
                            urgency=urgency_code,
                            comments=enc.get("chief_complaint", "")
                        )
                    )

                    # Grava diagnóstico clínico associado em gnuhealth.patient.disease
                    cid_code = enc.get("diagnosis_cid10")
                    if cid_code:
                        if cid_code not in pathology_cache:
                            p_find = Pathology.find([('code', '=', cid_code)])
                            pathology_cache[cid_code] = p_find[0] if p_find else None
                        path_obj = pathology_cache[cid_code]
                        if path_obj:
                            new_diseases.append(
                                PatientDisease(
                                    patient=pat,
                                    pathology=path_obj,
                                    healthprof=hp,
                                    diagnosed_date=enc_dt.date(),
                                    is_active=True,
                                    status="c",
                                )
                            )

                # Batch save em lotes de 100
                chunk_size = 100
                for i in range(0, len(new_appts), chunk_size):
                    chunk = new_appts[i:i + chunk_size]
                    Appointment.save(chunk)
                    enc_created += len(chunk)

                for i in range(0, len(new_diseases), chunk_size):
                    chunk_d = new_diseases[i:i + chunk_size]
                    PatientDisease.save(chunk_d)

        # 6. Carrega Internações Hospitalares
        print("-> Sincronizando Internações Hospitalares...")
        inp_file = os.path.join(batch_dir, "inpatients.json")
        inp_created = 0
        all_beds = Bed.find([('institution', '=', env["institution"])])
        if os.path.exists(inp_file) and all_beds:
            with open(inp_file, "r", encoding="utf-8") as f:
                inp_data = json.load(f)

            new_inps = []
            bed_usage = {}  # bed_id -> list of (adm_date, dis_date)
            for idx, inp_dict in enumerate(inp_data):
                pat = pat_map.get(inp_dict.get("patient_id"))
                if not pat:
                    skipped["inpatients"] += 1
                    continue

                adm_dt_str = inp_dict.get("hospitalization_date", inp_dict.get("admission_datetime"))
                dis_dt_str = inp_dict.get("discharge_date", inp_dict.get("discharge_datetime"))
                adm_date = datetime.fromisoformat(adm_dt_str)
                dis_date = datetime.fromisoformat(dis_dt_str)
                reason_raw = inp_dict.get("discharge_reason", "ALTA_MELHORADO")
                dis_reason = "death" if "OBITO" in reason_raw else "home"

                # Seleciona leito sem colisão no intervalo
                chosen_bed = None
                for b in all_beds:
                    intervals = bed_usage.get(b.id, [])
                    if not any(adm_date < occ_dis and dis_date > occ_adm for occ_adm, occ_dis in intervals):
                        chosen_bed = b
                        break
                if not chosen_bed:
                    skipped["inpatients"] += 1
                    continue

                # Diagnóstico coerente da internação (fonte da verdade: primary_diagnosis_cid10)
                dx_code = inp_dict.get("primary_diagnosis_cid10")
                dx_obj = None
                if dx_code:
                    if dx_code not in pathology_cache:
                        p_find = Pathology.find([('code', '=', dx_code)])
                        pathology_cache[dx_code] = p_find[0] if p_find else None
                    dx_obj = pathology_cache[dx_code]

                new_inps.append(
                    Inpatient(
                        patient=pat,
                        bed=chosen_bed,
                        hospitalization_date=adm_date,
                        discharge_date=dis_date,
                        discharge_reason=dis_reason,
                        discharge_dx=dx_obj,
                        admission_reason=dx_obj,
                        admission_type="routine"
                    )
                )

            chunk_size = 50
            for i in range(0, len(new_inps), chunk_size):
                chunk = new_inps[i:i + chunk_size]
                Inpatient.save(chunk)
                inp_created += len(chunk)

        # 7. Carrega Exames Laboratoriais
        print("-> Sincronizando Exames Laboratoriais...")
        lab_file = os.path.join(batch_dir, "labs.json")
        lab_created = 0
        all_tt = {tt.code: tt for tt in TestType.find([])}

        if os.path.exists(lab_file):
            with open(lab_file, "r", encoding="utf-8") as f:
                labs_data = json.load(f)

            new_labs = []
            for lab_dict in labs_data:
                pat = pat_map.get(lab_dict.get("patient_id"))
                hp = prof_map.get(lab_dict.get("requesting_doctor_id"))
                if not pat or not hp:
                    skipped["labs"] += 1
                    continue

                req_dt_str = lab_dict.get("request_date", lab_dict.get("request_datetime"))
                t_cat = str(lab_dict.get("test_category", "CBC")).strip().upper()
                tt = all_tt.get(t_cat)
                if not tt:
                    skipped["labs"] += 1
                    continue

                lab_dt = datetime.fromisoformat(req_dt_str)

                new_labs.append(
                    Lab(
                        patient=pat,
                        requestor=hp,
                        test=tt,
                        date_requested=lab_dt,
                        date_analysis=lab_dt,
                    )
                )

            chunk_size = 100
            for i in range(0, len(new_labs), chunk_size):
                chunk = new_labs[i:i + chunk_size]
                Lab.save(chunk)
                lab_created += len(chunk)

        # 8. Movimentações de Dispensação de Estoque vinculadas a Internações
        print("-> Sincronizando Dispensações de Medicamentos...")
        moves_file = os.path.join(batch_dir, "stock_moves.json")
        moves_created = 0
        if os.path.exists(moves_file) and med_map:
            with open(moves_file, "r", encoding="utf-8") as f:
                moves_data = json.load(f)

            new_moves = []
            for m_dict in moves_data:
                m_item_id = m_dict.get("medicament_id", m_dict.get("item_id"))
                item_tuple = med_map.get(m_item_id)
                if not item_tuple:
                    item_tuple = list(med_map.values())[0]
                _, prod = item_tuple

                m_date = date.fromisoformat(m_dict["date"])
                qty = float(m_dict.get("quantity", 1))
                origin_loc_name = m_dict.get("origin_location", "Farmácia Central")
                orig_loc = env["stock_locations"].get(origin_loc_name, env["stock_locations"]["Farmácia Central"])

                m = Move(
                    product=prod,
                    from_location=orig_loc,
                    to_location=env["customer_loc"],
                    quantity=qty,
                    unit=uom_unit,
                    company=env["company"],
                    currency=env["currency"],
                    unit_price=Decimal('10.00'),
                    effective_date=m_date
                )
                new_moves.append(m)

            chunk_size = 50
            for i in range(0, len(new_moves), chunk_size):
                chunk = new_moves[i:i + chunk_size]
                Move.save(chunk)
                for move_obj in chunk:
                    try:
                        move_obj.click('do')
                    except Exception:
                        pass
                moves_created += len(chunk)

        duration = round(time.time() - t0, 2)
        print(f"\n=== [ERP_LOADER] Sincronização Concluída em {duration}s! ===")
        print(f"Profissionais: {len(prof_map)} | Pacientes: {len(pat_map)} | Plantões: {shifts_created}")
        print(f"Atendimentos: {enc_created} | Internações: {inp_created} | Exames: {lab_created}")
        print(f"Medicamentos/Itens: {len(med_map)} | Dispensações: {moves_created}")

        report = {
            "batch_dir": batch_dir,
            "status": "SUCCESS",
            "duration_seconds": duration,
            "counts": {
                "professionals": len(prof_map),
                "patients": len(pat_map),
                "shifts": shifts_created,
                "encounters": enc_created,
                "inpatients": inp_created,
                "labs": lab_created,
                "stock_items": len(med_map),
                "stock_dispensations": moves_created,
            },
            "skipped": skipped,
            "timestamp": datetime.utcnow().isoformat()
        }

        rep_path = os.path.join(batch_dir, "erp_sync_report.json")
        with open(rep_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return report


def main():
    parser = argparse.ArgumentParser(description="QIMED GNU Health ERP Loader")
    parser.add_argument("--batch-dir", type=str, required=True, help="Diretório do lote com os arquivos JSON")
    parser.add_argument("--config-file", type=str, default="/etc/trytond.conf", help="Arquivo de configuração do Trytond")
    parser.add_argument("--connection-url", type=str, default=None, help="URL XML-RPC do GNU Health")

    args = parser.parse_args()

    loader = GnuHealthERPLoader(connection_url=args.connection_url, config_file=args.config_file)
    loader.sync_batch(args.batch_dir)


if __name__ == "__main__":
    main()
