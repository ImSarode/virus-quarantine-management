"""System Admin pages: admissions, staff accounts, bed status, approved closure, reports."""
import sqlite3
import pandas as pd
import streamlit as st
import database as db
from dashboard import patient_table,patient_label


def render(user):
    st.caption(f"Logged in as {user['name']} · {user['id']}")
    tabs=st.tabs(['Patient management','Beds','Discharge / mortality','Staff accounts','Reports & activity'])
    with tabs[0]:
        st.subheader('Admit patient')
        beds=db.available_beds()
        if not beds:
            st.error('Facility is full (74/74). Admission cannot proceed.')
        else:
            bed_map={b['id']:b['room'] for b in beds}
            with st.form('admit_patient_form'):
                name=st.text_input('Full name')
                age=st.number_input('Age',0,120,30)
                bed=st.selectbox('Available bed',[b['id'] for b in beds],
                                 format_func=lambda b:f'Bed {b:02d} · {bed_map[b]}')
                submit=st.form_submit_button('Register and assign bed',type='primary')
            if submit:
                try:
                    db.admit(user,name,age,bed)
                    st.success('Patient admitted.')
                    st.rerun()
                except (ValueError,PermissionError,sqlite3.IntegrityError) as ex: st.error(str(ex))
        st.subheader('Current patient list')
        patient_table(db.active_patients())
        with st.expander('All patients including historic outcomes'):
            st.dataframe(pd.DataFrame(db.all_patients()),use_container_width=True,hide_index=True)
    with tabs[1]:
        st.subheader('Bed management')
        active=db.active_patients()
        st.progress(len(active)/db.CAPACITY,text=f'{len(active)} of {db.CAPACITY} beds occupied')
        used={p['bed_id']:p for p in active}
        records=[{'Bed':i,'Room':f"Room {(i-1)//2+1:02d}",
                  'Status':'Occupied' if i in used else 'Free',
                  'Patient':used[i]['name'] if i in used else '—'} for i in range(1,75)]
        bed_status=st.radio('Filter beds',['All','Free','Occupied'],horizontal=True)
        if bed_status!='All':
            records=[r for r in records if r['Status']==bed_status]
        st.dataframe(pd.DataFrame(records),use_container_width=True,hide_index=True)
    with tabs[2]:
        st.subheader('Doctor-approved bed releases')
        approved=[p for p in db.active_patients() if p['status'] in ('Discharge Approved','Death Approved')]
        if not approved:
            st.info('No approved patient removals are pending.')
        for p in approved:
            with st.container(border=True):
                st.write(f"**{patient_label(p)}** · {p['status']} · Doctor: {p['approved_by']}")
                label='Confirm discharge and free bed' if p['status']=='Discharge Approved' else 'Confirm mortality and free bed'
                if st.button(label,key=f"close_{p['id']}",type='primary'):
                    try:
                        db.close_patient(user,p['id'])
                        st.rerun()
                    except (ValueError,PermissionError) as ex: st.error(str(ex))
        st.caption('No permanent deletion: completed patient records remain in SQLite for outcome reporting.')
    with tabs[3]:
        st.subheader('Nurse, doctor, and administrator accounts')
        st.dataframe(pd.DataFrame(db.users()),use_container_width=True,hide_index=True)
        with st.expander('Add new staff account'):
            with st.form('new_user_form'):
                uid=st.text_input('Staff ID (e.g., N003)')
                name=st.text_input('Staff name')
                role=st.selectbox('Role',['Nurse','Doctor','Admin'])
                password=st.text_input('Temporary password',type='password')
                submit=st.form_submit_button('Create staff account')
            if submit:
                try:
                    db.add_user(user,uid,name,role,password)
                    st.rerun()
                except (ValueError,PermissionError,sqlite3.IntegrityError) as ex: st.error(str(ex))
        with st.expander('Activate / deactivate staff'):
            accounts=db.users()
            ids=[u['id'] for u in accounts]
            if ids:
                uid=st.selectbox('Choose account',ids,key='staff_account')
                account=next(u for u in accounts if u['id']==uid)
                st.write('Currently:','Active' if account['active'] else 'Inactive')
                if st.button('Toggle active status'):
                    try:
                        db.set_user_active(user,uid,not account['active'])
                        st.rerun()
                    except (ValueError,PermissionError) as ex: st.error(str(ex))
    with tabs[4]:
        st.subheader('Facility reports')
        stats=db.outcome_stats()
        a,b,c=st.columns(3)
        a.metric('Recovered / alive',stats['alive'])
        b.metric('Deceased',stats['deceased'])
        c.metric('Survival rate',f"{stats['survival_pct']}%")
        if stats['completed']:
            st.bar_chart(pd.DataFrame({'Patients':[stats['alive'],stats['deceased']]},index=['Alive','Deceased']))
            st.caption(f"Mortality = {stats['deceased']} / {stats['completed']} completed outcomes = {stats['mortality_pct']}%. Active patients excluded.")
        else: st.info('No completed outcomes yet.')
        st.subheader('Notifications / recent actions')
        waiting=[p for p in db.active_patients() if p['status'] in ('Discharge Approved','Death Approved')]
        if waiting: st.warning(f'{len(waiting)} patient(s) approved and waiting for bed release.')
        else: st.success('No pending doctor-approved discharges or mortality cases.')
        activity=db.events()
        if activity: st.dataframe(pd.DataFrame(activity),use_container_width=True,hide_index=True)
