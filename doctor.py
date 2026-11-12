"""Doctor pages: trends, consultations, treatment history, patient details, approvals."""
import streamlit as st
import pandas as pd
import database as db
from dashboard import patient_table,select_patient,temperature_history,patient_label


def render(user):
    st.caption(f"Logged in as {user['name']} · {user['id']}")
    tabs=st.tabs(['Patients & trends','Doctor visits / treatment','Visit history','Discharge / mortality','Patient details'])
    with tabs[0]:
        st.subheader('Patients and temperature trends')
        patient_table(db.active_patients())
        pid=select_patient('d_trend')
        if pid is not None:
            st.caption(f"Consecutive completed fever-free days: {db.fever_free_days(pid)}")
            temperature_history(pid,chart=True)
    with tabs[1]:
        st.subheader('Record doctor visit')
        pid=select_patient('d_visit')
        if pid is not None:
            t=db.today_temp(pid)
            v=db.today_visit(pid)
            if t:
                st.success(f"Today's nurse reading: {t['temp_c']:.1f}°C")
            else:
                st.warning('Daily temperature not yet recorded. Coordinate with nurse. Urgent visit may proceed.')
            if v:
                st.info(f"Visit completed today by {v['doctor_id']}. Treatment and notes are saved.")
            else:
                with st.form('visit_form'):
                    notes=st.text_area('Visit notes')
                    treatment=st.text_area('Treatment plan / action')
                    submit=st.form_submit_button('Save visit and mark completed',type='primary')
                if submit:
                    try:
                        db.record_visit(user,pid,notes,treatment)
                        st.success('Visit completed.')
                        st.rerun()
                    except (ValueError,PermissionError) as ex: st.error(str(ex))
    with tabs[2]:
        st.subheader('Doctor visitation and treatment records')
        pid=select_patient('d_visits_history')
        if pid is not None:
            rows=db.visits(pid)
            if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
            else: st.info('No previous visits recorded.')
    with tabs[3]:
        st.subheader('Discharge eligibility and mortality approvals')
        st.caption('Demo rule: 3 complete prior days, each with a normal temperature and no-fever report. A clinician must confirm the real-world protocol.')
        patients=db.active_patients()
        for p in patients:
            if p['status']!='Admitted': continue
            days=db.fever_free_days(p['id'])
            with st.container(border=True):
                st.write(f"**{patient_label(p)}** · {days} completed fever-free days")
                left,right=st.columns(2)
                if left.button('Approve discharge',key=f"dis_{p['id']}",disabled=days<3):
                    try:
                        db.approve_outcome(user,p['id'],'Discharge Approved')
                        st.rerun()
                    except (ValueError,PermissionError) as ex: st.error(str(ex))
                with right.popover('Record death / approve bed release'):
                    st.warning('Use only for a confirmed death. This is a fictional prototype.')
                    if st.button('Confirm death approval',key=f"death_{p['id']}"):
                        try:
                            db.approve_outcome(user,p['id'],'Death Approved')
                            st.rerun()
                        except (ValueError,PermissionError) as ex: st.error(str(ex))
        approved=[p for p in patients if p['status'] in ('Discharge Approved','Death Approved')]
        if approved:
            st.subheader('Awaiting admin processing')
            for p in approved: st.info(f"{patient_label(p)} — {p['status']}")
    with tabs[4]:
        st.subheader('Edit patient information')
        pid=select_patient('d_edit')
        if pid is not None:
            p=db.patient(pid)
            with st.form('edit_patient_form'):
                name=st.text_input('Patient name',value=p['name'])
                age=st.number_input('Age',min_value=0,max_value=120,value=p['age'])
                submit=st.form_submit_button('Save changes')
            if submit:
                try:
                    db.update_patient(user,pid,name,age)
                    st.success('Patient details updated.')
                    st.rerun()
                except (ValueError,PermissionError) as ex: st.error(str(ex))
