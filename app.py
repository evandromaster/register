
# A very simple Flask Hello World app for you to get started with...
import json
import hashlib
import base64
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv(
    'SECRET_KEY', 'your-secret-key-change-this')

# Database Configuration - supports both PostgreSQL and SQLite for development
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///users.db')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Allowed extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


# Load enterprise data
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENTERPRISE_JSON_PATH = os.path.join(BASE_DIR, 'enterprise.json')
CITYZEN_JSON_PATH = os.path.join(BASE_DIR, 'cityzen.json')


def load_enterprise_data():
    with open(ENTERPRISE_JSON_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_cityzen_data():
    with open(CITYZEN_JSON_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_unique_municipalities():
    """Extract unique municipalities from cityzen.json"""
    cityzen_data = load_cityzen_data()
    municipalities = list(set([item['MUNICIPIO'] for item in cityzen_data]))
    return sorted(municipalities)


ENTERPRISE_DATA = load_enterprise_data()
MUNICIPALITIES = get_unique_municipalities()

# Initialize database
db = SQLAlchemy(app)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Define models here to avoid circular imports


class UserRegistration(db.Model):
    __tablename__ = 'user_registration'
    id = db.Column(db.Integer, primary_key=True)
    infopen = db.Column(db.String(100), unique=True, nullable=True)
    nome_completo = db.Column(db.String(200), nullable=False)
    cpf = db.Column(db.String(14), nullable=True)  # Added CPF field
    rua = db.Column(db.String(200), nullable=True)
    bairro = db.Column(db.String(200), nullable=True)
    numero = db.Column(db.String(20), nullable=True)
    municipio = db.Column(db.String(100), nullable=True)
    ueop = db.Column(db.String(100), nullable=True)
    cia = db.Column(db.String(100), nullable=True)
    restricoes_judiciais = db.Column(db.Text, nullable=True)
    imagem_perfil = db.Column(
        db.String(200), nullable=True)  # Added image field
    # SHA256 hash of the image
    image_hash = db.Column(db.String(64), nullable=True)
    latitude = db.Column(db.String(20), nullable=True)  # Latitude field
    longitude = db.Column(db.String(20), nullable=True)  # Longitude field
    data_modificacao = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<UserRegistration {self.nome_completo}>'


class Images(db.Model):
    __tablename__ = 'images'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # Foreign key relationship with user_registration.infopen
    infopen = db.Column(db.String(100), nullable=False)
    # Store Base64 encoded image
    image_b64 = db.Column(db.Text, nullable=False)
    # Optional datetime field
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Images {self.infopen}>'


# Create tables only if they don't exist
with app.app_context():
    # Check if tables exist, create them if they don't
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()

    if 'images' not in table_names:  # If images table doesn't exist, create all tables
        db.create_all()
    else:
        # Add new columns if they don't exist in user_registration
        from sqlalchemy import text

        result = db.session.execute(
            text("PRAGMA table_info(user_registration)"))
        columns = [row[1] for row in result.fetchall()]

        if 'latitude' not in columns:
            db.session.execute(
                text("ALTER TABLE user_registration ADD COLUMN latitude VARCHAR(20)"))
        if 'longitude' not in columns:
            db.session.execute(
                text("ALTER TABLE user_registration ADD COLUMN longitude VARCHAR(20)"))
        if 'image_hash' not in columns:
            db.session.execute(
                text("ALTER TABLE user_registration ADD COLUMN image_hash VARCHAR(64)"))

        # Rename logradouro column to bairro if it exists
        if 'logradouro' in columns and 'bairro' not in columns:
            # Create the new bairro column
            db.session.execute(
                text("ALTER TABLE user_registration ADD COLUMN bairro VARCHAR(200)"))
            # Copy data from logradouro to bairro
            db.session.execute(
                text("UPDATE user_registration SET bairro = logradouro"))
            # Since SQLite doesn't support DROP COLUMN directly, we'll keep both columns
            # but the application will use the new 'bairro' column going forward

        db.session.commit()


@app.route('/')
def index():
    return redirect(url_for('register'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        infopen = request.form.get('infopen')
        nome_completo = request.form.get('nome_completo')
        cpf = request.form.get('cpf')
        rua = request.form.get('rua')
        bairro = request.form.get('bairro')
        numero = request.form.get('numero')
        municipio = request.form.get('municipio')
        ueop = request.form.get('ueop')
        cia = request.form.get('cia')
        restricoes_judiciais = request.form.get('restricoes_judiciais')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')

        # Backend validation for infopen field
        if not infopen or not infopen.strip():
            flash('O campo Infopen é obrigatório.', 'error')
            return render_template('register.html', enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)

        # Check if infopen already exists to ensure uniqueness
        existing_user = UserRegistration.query.filter_by(infopen=infopen).first()
        if existing_user:
            flash('Egresso já cadastrado!', 'error')
            return render_template('register.html', enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)

        # Handle image upload - convert to Base64 and store in images table
        imagem_perfil = None
        image_hash = None
        if 'imagem_perfil' in request.files:
            file = request.files['imagem_perfil']
            if file and file.filename != '' and allowed_file(file.filename):
                # Read the file content
                file_content = file.read()

                # Calculate the SHA256 hash of the image file
                image_hash = hashlib.sha256(file_content).hexdigest()

                # Convert the image to Base64
                image_b64 = base64.b64encode(file_content).decode('utf-8')

                # Store the Base64 image in the images table
                # First, check if an image already exists for this infopen and delete it
                existing_image = Images.query.filter_by(
                    infopen=infopen).first()
                if existing_image:
                    db.session.delete(existing_image)

                # Create new image record
                new_image = Images(
                    infopen=infopen,
                    image_b64=image_b64
                )
                db.session.add(new_image)

                # For backward compatibility, we still set imagem_perfil to the infopen
                # to indicate that an image exists for this user
                imagem_perfil = infopen

        # Create new user registration
        new_user = UserRegistration(
            infopen=infopen,
            nome_completo=nome_completo,
            cpf=cpf,
            rua=rua,
            bairro=bairro,
            numero=numero,
            municipio=municipio,
            ueop=ueop,
            cia=cia,
            restricoes_judiciais=restricoes_judiciais,
            imagem_perfil=imagem_perfil,
            image_hash=image_hash,
            latitude=latitude,
            longitude=longitude
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registro salvo com sucesso!', 'success')
            return redirect(url_for('register'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao salvar o registro: {str(e)}', 'error')

    # Prepare enterprise data and municipalities for the template
    return render_template('register.html', enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)


@app.route('/search', methods=['GET', 'POST'])
def search():
    users = []
    if request.method == 'POST':
        # Get filter values
        infopen = request.form.get('infopen')
        nome_completo = request.form.get('nome_completo')
        cpf = request.form.get('cpf')
        municipio = request.form.get('municipio')
        ueop = request.form.get('ueop')
        cia = request.form.get('cia')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')

        # Build query with filters
        query = UserRegistration.query

        if infopen:
            query = query.filter(
                UserRegistration.infopen.ilike(f'%{infopen}%'))
        if nome_completo:
            query = query.filter(
                UserRegistration.nome_completo.ilike(f'%{nome_completo}%'))
        if cpf:
            query = query.filter(UserRegistration.cpf.ilike(f'%{cpf}%'))
        if municipio:
            query = query.filter(
                UserRegistration.municipio.ilike(f'%{municipio}%'))
        if ueop:
            query = query.filter(UserRegistration.ueop.ilike(f'%{ueop}%'))
        if cia:
            query = query.filter(UserRegistration.cia.ilike(f'%{cia}%'))
        if latitude:
            query = query.filter(
                UserRegistration.latitude.ilike(f'%{latitude}%'))
        if longitude:
            query = query.filter(
                UserRegistration.longitude.ilike(f'%{longitude}%'))

        users = query.all()

    # Prepare enterprise data for the template
    return render_template('search.html', users=users, enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)


@app.route('/edit/<int:user_id>', methods=['GET', 'POST'])
def edit(user_id):
    user = UserRegistration.query.get_or_404(user_id)

    if request.method == 'POST':
        # Update user data
        infopen = request.form.get('infopen')

        # Backend validation for infopen field
        if not infopen or not infopen.strip():
            flash('O campo Infopen é obrigatório.', 'error')
            return render_template('edit.html', user=user, enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)

        # Check if infopen already exists for a different user (avoiding self-conflict)
        existing_user = UserRegistration.query.filter(
            UserRegistration.infopen == infopen,
            UserRegistration.id != user_id  # Exclude current user from check
        ).first()
        if existing_user:
            flash('Egresso já cadastrado!', 'error')
            return render_template('edit.html', user=user, enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)

        user.infopen = infopen
        user.nome_completo = request.form.get('nome_completo')
        user.cpf = request.form.get('cpf')
        user.rua = request.form.get('rua')
        user.bairro = request.form.get('bairro')
        user.numero = request.form.get('numero')
        user.municipio = request.form.get('municipio')
        user.ueop = request.form.get('ueop')
        user.cia = request.form.get('cia')
        user.restricoes_judiciais = request.form.get('restricoes_judiciais')
        user.latitude = request.form.get('latitude')
        user.longitude = request.form.get('longitude')

        # Handle image upload - convert to Base64 and store in images table
        if 'imagem_perfil' in request.files:
            file = request.files['imagem_perfil']
            if file and file.filename != '' and allowed_file(file.filename):
                # Read the file content
                file_content = file.read()

                # Calculate the SHA256 hash of the image file
                user.image_hash = hashlib.sha256(file_content).hexdigest()

                # Convert the image to Base64
                image_b64 = base64.b64encode(file_content).decode('utf-8')

                # Store the Base64 image in the images table
                # First, check if an image already exists for this infopen and delete it
                existing_image = Images.query.filter_by(
                    infopen=user.infopen).first()
                if existing_image:
                    db.session.delete(existing_image)

                # Create new image record
                new_image = Images(
                    infopen=user.infopen,
                    image_b64=image_b64
                )
                db.session.add(new_image)

                # For backward compatibility, we still set imagem_perfil to the infopen
                # to indicate that an image exists for this user
                user.imagem_perfil = user.infopen

        try:
            db.session.commit()
            flash('Registro atualizado com sucesso!', 'success')
            return redirect(url_for('search'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar o registro: {str(e)}', 'error')

    return render_template('edit.html', user=user, enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)

# Add route to serve Base64 images from the database


@app.route('/image/<infopen>')
def get_image(infopen):
    image_record = Images.query.filter_by(infopen=infopen).first()
    if image_record:
        # Decode the Base64 image and return it
        image_data = base64.b64decode(image_record.image_b64)
        from flask import Response
        import io
        # Determine content type based on image data
        if image_data.startswith(b'\x89PNG\r\n\x1a\n'):
            content_type = 'image/png'
        elif image_data.startswith(b'\xff\xd8\xff'):
            content_type = 'image/jpeg'
        elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
            content_type = 'image/gif'
        else:
            content_type = 'image/jpeg'  # default

        return Response(image_data, mimetype=content_type)
    else:
        # Return a default image or 404
        from flask import abort
        abort(404)


# Route for the interactive map modal
@app.route('/map')
def map():
    return render_template('map.html')


@app.route('/delete/<int:user_id>', methods=['POST'])
def delete(user_id):
    user = UserRegistration.query.get_or_404(user_id)

    try:
        # Delete the user's profile image from the images table if it exists
        existing_image = Images.query.filter_by(infopen=user.infopen).first()
        if existing_image:
            db.session.delete(existing_image)

        # Delete the user from the database
        db.session.delete(user)
        db.session.commit()
        flash('Registro excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir o registro: {str(e)}', 'error')

    return redirect(url_for('search'))


@app.route('/export_csv', methods=['POST'])
def export_csv():
    # Get filter values from the form (same as in search route)
    infopen = request.form.get('infopen')
    nome_completo = request.form.get('nome_completo')
    cpf = request.form.get('cpf')
    municipio = request.form.get('municipio')
    ueop = request.form.get('ueop')
    cia = request.form.get('cia')
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')

    # Build query with filters (same logic as in search route)
    query = UserRegistration.query

    if infopen:
        query = query.filter(
            UserRegistration.infopen.ilike(f'%{infopen}%'))
    if nome_completo:
        query = query.filter(
            UserRegistration.nome_completo.ilike(f'%{nome_completo}%'))
    if cpf:
        query = query.filter(UserRegistration.cpf.ilike(f'%{cpf}%'))
    if municipio:
        query = query.filter(
            UserRegistration.municipio.ilike(f'%{municipio}%'))
    if ueop:
        query = query.filter(UserRegistration.ueop.ilike(f'%{ueop}%'))
    if cia:
        query = query.filter(UserRegistration.cia.ilike(f'%{cia}%'))
    if latitude:
        query = query.filter(UserRegistration.latitude.ilike(f'%{latitude}%'))
    if longitude:
        query = query.filter(
            UserRegistration.longitude.ilike(f'%{longitude}%'))

    users = query.all()

    # Generate CSV content with UTF-8 BOM encoding
    import csv
    import io
    from flask import make_response

    # Create a string buffer
    output = io.StringIO()

    # Write header
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Infopen', 'Nome Completo', 'CPF', 'Rua', 'Bairro',
        'Número', 'Município', 'UEOP', 'CIA', 'Restrições Judiciais',
        'Imagem de Perfil', 'Image Hash', 'Latitude', 'Longitude', 'Data de Modificação'
    ])

    # Write data rows
    for user in users:
        writer.writerow([
            user.id,
            user.infopen or '',
            user.nome_completo or '',
            user.cpf or '',
            user.rua or '',
            user.bairro or '',
            user.numero or '',
            user.municipio or '',
            user.ueop or '',
            user.cia or '',
            user.restricoes_judiciais or '',
            user.imagem_perfil or '',
            user.image_hash or '',  # Include the image hash in the export
            user.latitude or '',
            user.longitude or '',
            user.data_modificacao.strftime(
                '%d/%m/%Y %H:%M:%S') if user.data_modificacao else ''
        ])

    # Get the CSV content as string
    csv_content = output.getvalue()
    output.close()

    # Add UTF-8 BOM to the content
    csv_content_with_bom = '\ufeff' + csv_content

    # Create response with CSV content
    response = make_response(csv_content_with_bom)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=registros_exportados.csv'

    return response


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)


#if __name__ == '__main__':
#    app.run(host='0.0.0.0', debug=True)

