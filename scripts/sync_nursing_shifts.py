import json
import os
from datetime import datetime
from proteus import config, Model

config.set_trytond('gnuhealth', config_file='/etc/trytond.conf', user='admin')

Party = Model.get('party.party')
HealthProf = Model.get('gnuhealth.healthprofessional')
Specialty = Model.get('gnuhealth.specialty')
Inst = Model.get('gnuhealth.institution')
Cal = Model.get('calendar.calendar')
Event = Model.get('calendar.event')
CalLoc = Model.get('calendar.location')

inst = Inst.find([])[0]
cal = Cal.find([('name', '=', 'Escala Médica Hospitalar')])
if not cal:
    cal = Cal(name='Escala Médica Hospitalar', description='Plantão Médico e Enfermagem QIMED')
    cal.save()
else:
    cal = cal[0]

# 1. Carrega profissionais (especialmente equipe de enfermagem)
json_profs_path = '/app/data/synthetic_output/batch_fase_b_v1/professionals.json'
with open(json_profs_path, 'r', encoding='utf-8') as f:
    profs = json.load(f)

profs_created = 0
for p_dict in profs:
    p_name = p_dict['name']
    code = p_dict['id']
    spec_name = p_dict.get('specialty_name', 'Enfermagem Hospitalar')
    
    spec = Specialty.find([('name', '=', spec_name)])
    if not spec:
        spec = Specialty(name=spec_name, code=p_dict.get('specialty_code', spec_name[:4].upper()))
        spec.save()
    else:
        spec = spec[0]

    p = Party.find([('name', '=', p_name)])
    if not p:
        p = Party(
            name=p_name,
            is_person=True,
            is_healthprof=True,
            is_patient=False,
            create_target=False,
            gender=p_dict.get('gender', 'f' if 'Camila' in p_name or 'Maria' in p_name else 'm')
        )
        p.save()
    else:
        p = p[0]
        if p.is_patient:
            p.is_patient = False
            p.save()

    hp = HealthProf.find([('party', '=', p)])
    if not hp:
        hp = HealthProf(party=p, institution=inst, main_specialty=spec, code=code)
        hp.save()
        profs_created += 1

print(f'New health professionals created in ERP: {profs_created}')

# 2. Carrega eventos de escala (plantões médicos e de enfermagem)
json_shifts_path = '/app/data/synthetic_output/batch_fase_b_v1/shifts.json'
with open(json_shifts_path, 'r', encoding='utf-8') as f:
    shifts = json.load(f)

existing_events = {(e.summary, e.dtstart) for e in Event.find([('calendar', '=', cal)])}
cloc_map = {l.name: l for l in CalLoc.find([])}

new_events = []
for s in shifts:
    sector = s.get('ward', 'Pronto Socorro')
    cloc = cloc_map.get(sector)
    if not cloc:
        cloc = CalLoc(name=sector)
        cloc.save()
        cloc_map[sector] = cloc

    dtstart = datetime.fromisoformat(s['start_time'])
    dtend = datetime.fromisoformat(s['end_time'])
    summary = s.get('summary') or f"Plantão {s.get('professional_name')} ({sector})"

    if (summary, dtstart) not in existing_events:
        new_events.append(
            Event(
                calendar=cal,
                summary=summary,
                dtstart=dtstart,
                dtend=dtend,
                location=cloc,
                status='confirmed'
            )
        )

print(f'Total new shift events to save: {len(new_events)}')
for i in range(0, len(new_events), 100):
    chunk = new_events[i:i + 100]
    Event.save(chunk)

print(f'Successfully synced {len(new_events)} shifts (including nursing)!')
