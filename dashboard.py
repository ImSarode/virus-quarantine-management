"""Shared dashboard widgets. All numbers come from SQLite."""
import streamlit as st
import pandas as pd
import database as db


def patient_label(p):
    return f"#{p['id']:03d} · {p['name']} · Bed {p['bed_id']:02d}"


def select_patient(key, patients=None, label='Select patient'):
    patients = db.active_patients() if patients is None else patients
    if not patients:
        st.info('No patients available.')
        return None
    ids=[p['id'] for p in patients]
    return st.selectbox(label, ids,
                        format_func=lambda pid:patient_label(next(p for p in patients if p['id']==pid)),
                        key=key)


def patient_table(patients, daily=True):
    if not patients:
        st.info('No patients to display.')
        return
    rows=[]
    for p in patients:
        row={'ID':p['id'],'Name':p['name'],'Bed':p['bed_id'], 'Status':p['status']}
        if daily:
            row.update({'Temp today':'Done' if db.today_temp(p['id']) else 'Pending',
                        'Doctor today':'Done' if db.today_visit(p['id']) else 'Pending',
                        'Fever-free days':db.fever_free_days(p['id'])})
        rows.append(row)
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)


def temperature_history(pid, chart=False):
    readings=db.temperatures(pid)
    if not readings:
        st.info('No temperature readings yet.')
        return
    df=pd.DataFrame(readings)
    if chart:
        chart_df=df[['measured_day','temp_c']].copy().sort_values('measured_day')
        chart_df=chart_df.rename(columns={'measured_day':'Day','temp_c':'Temperature (°C)'})
        st.line_chart(chart_df.set_index('Day'))
    display=df[['measured_day','temp_c','reported_fever_free','checked_by']].rename(columns={
        'measured_day':'Date','temp_c':'Temperature °C',
        'reported_fever_free':'No fever reported','checked_by':'Nurse ID'})
    st.dataframe(display,use_container_width=True,hide_index=True)


def overview(role):
    active=db.active_patients()
    pending_temp=sum(db.today_temp(p['id']) is None for p in active)
    pending_visit=sum(db.today_visit(p['id']) is None for p in active)
    available=len(db.available_beds())
    st.subheader(f'{role} Dashboard')
    a,b,c,d=st.columns(4)
    a.metric('Admitted patients',len(active))
    b.metric('Available beds',available)
    c.metric('Temperature pending',pending_temp)
    d.metric('Doctor visits pending',pending_visit)
    if role=='Nurse':
        st.progress((len(active)-pending_temp)/len(active) if active else 1.0,
                    text=f"Daily checks completed: {len(active)-pending_temp}/{len(active)}")
    elif role=='Doctor':
        st.progress((len(active)-pending_visit)/len(active) if active else 1.0,
                    text=f"Doctor visits completed: {len(active)-pending_visit}/{len(active)}")
    else:
        stats=db.outcome_stats()
        x,y,z=st.columns(3)
        x.metric('Completed alive',stats['alive'])
        y.metric('Deaths',stats['deceased'])
        z.metric('Mortality rate',f"{stats['mortality_pct']}%")
        if stats['completed'] and stats['mortality_pct']>15:
            st.warning('Observed mortality exceeds the 15% benchmark. Small samples may be volatile.')
    st.divider()
