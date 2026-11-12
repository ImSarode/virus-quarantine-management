"""SQLite persistence and business rules for a fictional classroom demo.
Never use this prototype for real clinical decision-making or patient data.
"""
import hashlib
import hmac
import os
import secrets
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.getenv('MEDITRACK_DB', str(Path(tempfile.gettempdir()) / 'meditrack_v2.sqlite3')))
CAPACITY = 74
FEVER_C = 38.0  # illustrative threshold; clinician must approve any real-life protocol


def now():
    return datetime.now().isoformat(timespec='seconds')


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def password_hash(password):
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200_000)
    return salt.hex() + ':' + key.hex()


def verify_password(password, stored):
    try:
        salt, digest = stored.split(':')
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 200_000)
        return hmac.compare_digest(key, bytes.fromhex(digest))
    except (ValueError, AttributeError):
        return False


def query(statement, args=()):
    with connect() as conn:
        return [dict(x) for x in conn.execute(statement, args).fetchall()]


def one(statement, args=()):
    rows = query(statement, args)
    return rows[0] if rows else None


def audit(conn, user_id, action, patient_id=None):
    conn.execute('INSERT INTO audit_log(user_id,patient_id,action,created_at) VALUES (?,?,?,?)',
                 (user_id, patient_id, action, now()))


def init_db():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL
              CHECK(role IN ('Nurse','Doctor','Admin')),
            password TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS beds (
            id INTEGER PRIMARY KEY CHECK(id BETWEEN 1 AND 74), room TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, age INTEGER NOT NULL CHECK(age BETWEEN 0 AND 120),
            bed_id INTEGER NOT NULL REFERENCES beds(id),
            admitted_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Admitted' CHECK(status IN
                ('Admitted','Discharge Approved','Death Approved','Closed')),
            outcome TEXT CHECK(outcome IN ('Alive','Deceased') OR outcome IS NULL),
            approved_by TEXT REFERENCES users(id), approved_at TEXT,
            closed_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_patient_per_bed
          ON patients(bed_id) WHERE status != 'Closed';
        CREATE TABLE IF NOT EXISTS temperatures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            measured_day TEXT NOT NULL, temp_c REAL NOT NULL CHECK(temp_c BETWEEN 30 AND 45),
            reported_fever_free INTEGER NOT NULL DEFAULT 0,
            checked_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
            UNIQUE(patient_id,measured_day)
        );
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            visit_day TEXT NOT NULL, doctor_id TEXT NOT NULL REFERENCES users(id),
            notes TEXT NOT NULL, treatment TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(patient_id,visit_day)
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, patient_id INTEGER, action TEXT NOT NULL, created_at TEXT NOT NULL
        );
        ''')
        if c.execute('SELECT COUNT(*) FROM beds').fetchone()[0] == 0:
            c.executemany('INSERT INTO beds(id,room) VALUES (?,?)',
                          [(i, f'Room {(i-1)//2+1:02d}') for i in range(1,CAPACITY+1)])
        if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
            c.executemany('INSERT INTO users(id,name,role,password) VALUES (?,?,?,?)', [
                ('N001','Neha Sharma','Nurse', password_hash('demo123')),
                ('N002','Aditi Rao','Nurse', password_hash('demo123')),
                ('D001','Dr. Arjun Patel','Doctor',password_hash('demo123')),
                ('D002','Dr. Maya Shah','Doctor',password_hash('demo123')),
                ('A001','Samir Desai','Admin',password_hash('demo123')),
            ])
        if c.execute('SELECT COUNT(*) FROM patients').fetchone()[0] == 0:
            today = date.today()
            sample = [('Aarav Mehta',34,1,9),('Diya Kapoor',27,2,7),('Kabir Shah',46,3,6),
                      ('Sara Khan',38,4,5),('Riya Patel',29,5,5),('Dev Rao',51,6,5)]
            for idx,(name,age,bed,days) in enumerate(sample):
                p = c.execute('INSERT INTO patients(name,age,bed_id,admitted_at) VALUES (?,?,?,?)',
                              (name,age,bed,(today-timedelta(days=days)).isoformat()))
                for offset in (3,2,1):
                    day=(today-timedelta(days=offset)).isoformat()
                    temp=36.6+offset*.1 if idx==0 else (38.3 if idx in (1,3) and offset==2 else 37.0)
                    c.execute('''INSERT INTO temperatures(patient_id,measured_day,temp_c,
                        reported_fever_free,checked_by,created_at) VALUES (?,?,?,?,?,?)''',
                        (p.lastrowid,day,temp,int(temp<FEVER_C),'N001',day+'T09:00:00'))
            # Historical outcomes allow calculating non-empty reports from day one.
            for name,age,bed,outcome in [('Previous Patient A',61,7,'Alive'),
                                          ('Previous Patient B',72,8,'Alive'),
                                          ('Previous Patient C',54,9,'Alive'),
                                          ('Previous Patient D',69,10,'Deceased')]:
                c.execute('''INSERT INTO patients(name,age,bed_id,admitted_at,status,outcome,closed_at)
                             VALUES (?,?,?,?,'Closed',?,?)''',
                          (name,age,bed,(today-timedelta(days=12)).isoformat(),outcome,
                           (today-timedelta(days=3)).isoformat()))


def authenticate(user_id, password):
    user=one('SELECT * FROM users WHERE UPPER(id)=? AND active=1',(user_id.strip().upper(),))
    if user and verify_password(password,user['password']):
        return {key:user[key] for key in ('id','name','role')}
    return None


def users(role=None):
    if role:
        return query('SELECT id,name,role,active FROM users WHERE role=? ORDER BY id',(role,))
    return query('SELECT id,name,role,active FROM users ORDER BY role,id')


def require_role(user, *allowed):
    if not user or user.get('role') not in allowed:
        raise PermissionError('You do not have permission to do this.')
    current=one('SELECT active,role FROM users WHERE id=?',(user['id'],))
    if not current or not current['active'] or current['role']!=user['role']:
        raise PermissionError('This account is no longer active.')


def add_user(actor, user_id, name, role, password):
    require_role(actor,'Admin')
    user_id=user_id.strip().upper()
    if not user_id or not name.strip() or role not in ('Nurse','Doctor','Admin'):
        raise ValueError('Enter a valid staff ID, name and role.')
    if len(password)<6: raise ValueError('Password must be at least 6 characters.')
    with connect() as c:
        c.execute('INSERT INTO users(id,name,role,password) VALUES (?,?,?,?)',
                  (user_id,name.strip(),role,password_hash(password)))
        audit(c,actor['id'],f'Created {role} account {user_id}')


def set_user_active(actor,target_id,active):
    require_role(actor,'Admin')
    if actor['id']==target_id: raise ValueError('You cannot deactivate your own account.')
    with connect() as c:
        c.execute('UPDATE users SET active=? WHERE id=?',(int(active),target_id))
        audit(c,actor['id'],f'Set account {target_id} active={active}')


def active_patients():
    return query("SELECT p.*,b.room FROM patients p JOIN beds b ON p.bed_id=b.id WHERE p.status!='Closed' ORDER BY p.bed_id")


def all_patients():
    return query('SELECT p.*,b.room FROM patients p JOIN beds b ON p.bed_id=b.id ORDER BY p.id DESC')


def patient(pid):
    return one('SELECT * FROM patients WHERE id=?',(pid,))


def available_beds():
    return query('''SELECT b.id,b.room FROM beds b WHERE NOT EXISTS
                  (SELECT 1 FROM patients p WHERE p.bed_id=b.id AND p.status!='Closed') ORDER BY b.id''')


def admit(actor,name,age,bed_id):
    require_role(actor,'Admin')
    if not name.strip(): raise ValueError('Patient name is required.')
    if not 0<=int(age)<=120: raise ValueError('Invalid patient age.')
    with connect() as c:
        if not c.execute('SELECT id FROM beds WHERE id=?',(bed_id,)).fetchone():
            raise ValueError('Unknown bed.')
        if c.execute("SELECT id FROM patients WHERE bed_id=? AND status!='Closed'",(bed_id,)).fetchone():
            raise ValueError('This bed is already occupied.')
        cursor=c.execute('INSERT INTO patients(name,age,bed_id,admitted_at) VALUES (?,?,?,?)',
                         (name.strip(),int(age),int(bed_id),date.today().isoformat()))
        audit(c,actor['id'],'Patient admitted',cursor.lastrowid)


def update_patient(actor,pid,name,age):
    require_role(actor,'Doctor')
    if not name.strip() or not 0<=int(age)<=120: raise ValueError('Valid name and age required.')
    with connect() as c:
        if not c.execute('SELECT id FROM patients WHERE id=?',(pid,)).fetchone():
            raise ValueError('Patient not found.')
        c.execute('UPDATE patients SET name=?,age=? WHERE id=?',(name.strip(),int(age),pid))
        audit(c,actor['id'],'Patient details updated',pid)


def temperatures(pid):
    return query('''SELECT t.measured_day,t.temp_c,t.reported_fever_free,t.checked_by,t.created_at
                    FROM temperatures t WHERE patient_id=? ORDER BY measured_day DESC''',(pid,))


def visits(pid):
    return query('''SELECT visit_day,doctor_id,notes,treatment,created_at FROM visits
                    WHERE patient_id=? ORDER BY visit_day DESC''',(pid,))


def today_temp(pid):
    return one('SELECT * FROM temperatures WHERE patient_id=? AND measured_day=?',
               (pid,date.today().isoformat()))


def today_visit(pid):
    return one('SELECT * FROM visits WHERE patient_id=? AND visit_day=?',
               (pid,date.today().isoformat()))


def record_temperature(actor,pid,temp,reported_fever_free):
    require_role(actor,'Nurse')
    temp=float(temp)
    if not 30<=temp<=45: raise ValueError('Temperature must be between 30°C and 45°C.')
    with connect() as c:
        p=c.execute('SELECT status FROM patients WHERE id=?',(pid,)).fetchone()
        if not p or p['status']=='Closed': raise ValueError('Patient is not currently admitted.')
        if c.execute('SELECT id FROM temperatures WHERE patient_id=? AND measured_day=?',
                     (pid,date.today().isoformat())).fetchone():
            raise ValueError('Daily temperature check already completed.')
        c.execute('''INSERT INTO temperatures(patient_id,measured_day,temp_c,
                    reported_fever_free,checked_by,created_at) VALUES (?,?,?,?,?,?)''',
                  (pid,date.today().isoformat(),temp,int(bool(reported_fever_free) and temp<FEVER_C),
                   actor['id'],now()))
        audit(c,actor['id'],f'Recorded temperature {temp:.1f}°C',pid)


def record_visit(actor,pid,notes,treatment):
    require_role(actor,'Doctor')
    if not notes.strip() or not treatment.strip(): raise ValueError('Visit notes and treatment details are required.')
    with connect() as c:
        p=c.execute('SELECT status FROM patients WHERE id=?',(pid,)).fetchone()
        if not p or p['status']=='Closed': raise ValueError('Patient is not currently admitted.')
        if c.execute('SELECT id FROM visits WHERE patient_id=? AND visit_day=?',
                     (pid,date.today().isoformat())).fetchone():
            raise ValueError('Doctor visit already recorded today.')
        c.execute('''INSERT INTO visits(patient_id,visit_day,doctor_id,notes,treatment,created_at)
                     VALUES (?,?,?,?,?,?)''',
                  (pid,date.today().isoformat(),actor['id'],notes.strip(),treatment.strip(),now()))
        audit(c,actor['id'],'Completed doctor visit',pid)


def fever_free_days(pid):
    readings={r['measured_day']:r for r in temperatures(pid)}
    count=0
    d=date.today()-timedelta(days=1)  # only complete prior days qualify
    while (r:=readings.get(d.isoformat())) and r['temp_c']<FEVER_C and r['reported_fever_free']:
        count+=1
        d-=timedelta(days=1)
    return count


def approve_outcome(actor,pid,outcome):
    require_role(actor,'Doctor')
    if outcome not in ('Discharge Approved','Death Approved'): raise ValueError('Invalid outcome.')
    with connect() as c:
        p=c.execute('SELECT status FROM patients WHERE id=?',(pid,)).fetchone()
        if not p or p['status']!='Admitted': raise ValueError('Patient is not awaiting approval.')
        if outcome=='Discharge Approved' and fever_free_days(pid)<3:
            raise ValueError('Three complete consecutive fever-free days are required.')
        c.execute('UPDATE patients SET status=?,approved_by=?,approved_at=? WHERE id=?',
                  (outcome,actor['id'],now(),pid))
        audit(c,actor['id'],f'{outcome} by doctor',pid)


def close_patient(actor,pid):
    require_role(actor,'Admin')
    with connect() as c:
        p=c.execute('SELECT status FROM patients WHERE id=?',(pid,)).fetchone()
        if not p or p['status'] not in ('Discharge Approved','Death Approved'):
            raise ValueError('Doctor approval is required before bed release.')
        outcome='Alive' if p['status']=='Discharge Approved' else 'Deceased'
        c.execute("UPDATE patients SET status='Closed',outcome=?,closed_at=? WHERE id=?",
                  (outcome,now(),pid))
        audit(c,actor['id'],f'Patient closed: {outcome}; bed released',pid)


def outcome_stats():
    r=one('''SELECT SUM(CASE WHEN outcome='Alive' THEN 1 ELSE 0 END) alive,
             SUM(CASE WHEN outcome='Deceased' THEN 1 ELSE 0 END) deceased
             FROM patients WHERE status='Closed' ''')
    alive=int(r['alive'] or 0)
    dead=int(r['deceased'] or 0)
    total=alive+dead
    return {'alive':alive,'deceased':dead,'completed':total,
            'mortality_pct':round(dead/total*100,1) if total else 0.,
            'survival_pct':round(alive/total*100,1) if total else 0.}


def events(limit=30):
    return query('''SELECT created_at,user_id,patient_id,action FROM audit_log
                  ORDER BY id DESC LIMIT ?''',(limit,))
