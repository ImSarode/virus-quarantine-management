"""Streamlit entry point: staff-ID login and role-aware navigation."""
import streamlit as st
import database as db
import dashboard
import nurse
import doctor
import admin

st.set_page_config(page_title='MediTrack | Quarantine Facility',page_icon='🏥',layout='wide')
st.markdown('''<style>
.block-container{max-width:1350px;padding-top:1.5rem}
[data-testid="stMetric"]{background:#f0f6fc;border:1px solid #dbe6f2;padding:15px;border-radius:12px}
[data-testid="stSidebar"]{background:#f4f8fc}
.stButton button{border-radius:8px}
</style>''',unsafe_allow_html=True)

db.init_db()

if 'user' not in st.session_state:
    st.session_state.user=None

if st.session_state.user is None:
    st.title('🏥 MediTrack')
    st.subheader('Quarantine & Treatment Facility')
    st.caption('Educational prototype — fictional patients only')
    st.write('Sign in with your assigned **staff ID** and password.')
    left,right=st.columns([1,1])
    with left:
        with st.form('login'):
            staff_id=st.text_input('Staff ID',placeholder='N001 / D001 / A001')
            password=st.text_input('Password',type='password')
            submit=st.form_submit_button('Log in',type='primary',use_container_width=True)
        if submit:
            account=db.authenticate(staff_id,password)
            if account:
                st.session_state.user=account
                st.rerun()
            else:
                st.error('Invalid staff ID or password, or account inactive.')
    with right:
        st.info('**Demo accounts** (all passwords: `demo123`)\n\n'
                '- Nurse: `N001` or `N002`\n\n'
                '- Doctor: `D001` or `D002`\n\n'
                '- Admin: `A001`')
        st.caption('Role is determined automatically from the user’s SQLite account; it cannot be changed at login.')
    st.stop()

user=st.session_state.user
try:
    db.require_role(user,'Nurse','Doctor','Admin')
except PermissionError:
    st.session_state.user=None
    st.warning('Account access changed. Please sign in again.')
    st.rerun()

with st.sidebar:
    st.title('🏥 MediTrack')
    st.caption('QUARANTINE FACILITY · DEMO')
    st.write(f"**{user['name']}**")
    st.caption(f"{user['role']} · ID: {user['id']}")
    if st.button('Log out',use_container_width=True):
        st.session_state.user=None
        st.rerun()
    st.divider()
    st.caption('Patient records and interactions are fictional. The clinical rule is illustrative, not medical advice.')

st.title(f"{user['role']} Portal")
dashboard.overview(user['role'])
if user['role']=='Nurse':
    nurse.render(user)
elif user['role']=='Doctor':
    doctor.render(user)
elif user['role']=='Admin':
    admin.render(user)
