import os
import io
import secrets
import sqlite3
from datetime import datetime
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, abort, send_file, make_response)
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import qrcode

app = Flask(__name__)
app.secret_key = 'una_clave_secreta_muy_segura_123'

# ================= CONFIGURACIÓN DE RUTAS (ABSOLUTAS) =================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

CARPETA_FOTOS = os.path.join(STATIC_DIR, 'fotos')
CARPETA_UPLOADS = os.path.join(STATIC_DIR, 'uploads')

os.makedirs(CARPETA_FOTOS, exist_ok=True)
os.makedirs(CARPETA_UPLOADS, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB

DB_PATH = os.path.join(BASE_DIR, 'la_nueva_honduras.db')

# ================= CREAR BASE DE DATOS AUTOMÁTICAMENTE =================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellidos TEXT NOT NULL,
            sexo TEXT NOT NULL,
            fecha_nacimiento TEXT NOT NULL,
            correo TEXT UNIQUE NOT NULL,
            telefono TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            pais TEXT DEFAULT 'Honduras',
            departamento TEXT NOT NULL,
            municipio TEXT NOT NULL,
            localidad TEXT NOT NULL,
            tipo_participacion TEXT NOT NULL,
            dni TEXT UNIQUE NOT NULL,
            foto_ruta TEXT NOT NULL,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migración automática para agregar columnas del carnet
    cursor.execute("PRAGMA table_info(registros)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'token' not in columnas:
        cursor.execute("ALTER TABLE registros ADD COLUMN token TEXT")
    if 'activo' not in columnas:
        cursor.execute("ALTER TABLE registros ADD COLUMN activo INTEGER DEFAULT 1")

    # Generar tokens para registros existentes (si hay)
    cursor.execute("SELECT id FROM registros WHERE token IS NULL")
    for (row_id,) in cursor.fetchall():
        cursor.execute("UPDATE registros SET token = ? WHERE id = ?",
                       (secrets.token_urlsafe(16), row_id))

    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_registros_token ON registros(token)")

    conn.commit()
    conn.close()

init_db()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ================= RUTA PRINCIPAL =================
@app.route('/', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre']
        apellidos = request.form['apellidos']
        sexo = request.form['sexo']
        fecha_nacimiento = request.form['fecha_nacimiento']
        correo = request.form['correo']
        telefono = request.form['telefono']
        password = request.form['password']
        pais = request.form['pais']
        departamento = request.form['departamento']
        municipio = request.form['municipio']
        localidad = request.form['localidad']
        tipo_participacion = request.form['tipo_participacion']
        dni = request.form['dni']

        foto = request.files['foto']
        if foto and foto.filename != '':
            filename = secure_filename(f"{dni}_{foto.filename}")
            ruta_guardado = os.path.join(CARPETA_FOTOS, filename)
            foto.save(ruta_guardado)
            foto_ruta = f"static/fotos/{filename}"
        else:
            flash('La fotografía es obligatoria.', 'danger')
            return redirect(url_for('registro'))

        password_hash = generate_password_hash(password)
        token = secrets.token_urlsafe(16)

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO registros 
                (nombre, apellidos, sexo, fecha_nacimiento, correo, telefono, password_hash, 
                 pais, departamento, municipio, localidad, tipo_participacion, dni, foto_ruta,
                 token, activo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (nombre, apellidos, sexo, fecha_nacimiento, correo, telefono, password_hash,
                  pais, departamento, municipio, localidad, tipo_participacion, dni, foto_ruta,
                  token))
            conn.commit()
            conn.close()

            flash('¡Registro exitoso! Tu carnet digital ya está listo.', 'success')
            return redirect(url_for('carnet_exito', token=token))

        except sqlite3.IntegrityError:
            flash('Hubo un error. Es posible que ese correo o DNI ya estén registrados.', 'danger')
            return redirect(url_for('registro'))
        except Exception as e:
            print(f"Error inesperado: {e}")
            flash('Ocurrió un error inesperado al guardar.', 'danger')
            return redirect(url_for('registro'))

    return render_template('registro.html')


# ===== Pantalla de éxito post-registro =====
@app.route('/registro-exitoso/<token>')
def carnet_exito(token):
    conn = get_db()
    r = conn.execute("SELECT * FROM registros WHERE token = ?", (token,)).fetchone()
    conn.close()
    if not r:
        abort(404)
    url_carnet = url_for('ver_carnet', token=token, _external=True)
    return render_template('carnet_exito.html', r=r, url_carnet=url_carnet)


# ===== Acceso directo al carnet =====
@app.route('/carnet/<token>')
def ver_carnet(token):
    conn = get_db()
    r = conn.execute(
        "SELECT * FROM registros WHERE token = ? AND activo = 1", (token,)
    ).fetchone()
    conn.close()
    if not r:
        abort(404)
    resp = make_response(render_template('carnet.html', r=r))
    resp.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return resp


# ===== Generación del QR =====
@app.route('/carnet/<token>/qr.png')
def carnet_qr(token):
    conn = get_db()
    r = conn.execute(
        "SELECT id FROM registros WHERE token = ? AND activo = 1", (token,)
    ).fetchone()
    conn.close()
    if not r:
        abort(404)
    url = url_for('ver_carnet', token=token, _external=True)
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

   if __name__ == '__main__':
      port = int(os.environ.get('PORT', 5000)) # ¡Con 4 espacios al inicio!
      app.run(host='0.0.0.0', port=port)

