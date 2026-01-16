
# A very simple Flask Hello World app for you to get started with...
import json
import hashlib
import base64
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from zoneinfo import ZoneInfo
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from sqlalchemy import event

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

def get_current_time_brasilia():
    return datetime.now(ZoneInfo("America/Sao_Paulo"))

# Define models here to avoid circular imports


class UserRegistration(db.Model):
    __tablename__ = 'user_registration'
    id = db.Column(db.Integer, primary_key=True)
    infopen = db.Column(db.String(100), unique=True, nullable=True)
    nome_completo = db.Column(db.String(200), nullable=False)
    cpf = db.Column(db.String(14), nullable=True)  # Added CPF field
    telefone = db.Column(db.String(20), nullable=True)  # Added telefone field
    rua = db.Column(db.String(200), nullable=True)
    bairro = db.Column(db.String(200), nullable=True)
    numero = db.Column(db.String(20), nullable=True)
    municipio = db.Column(db.String(100), nullable=True)
    ueop = db.Column(db.String(100), nullable=True)
    cia = db.Column(db.String(100), nullable=True)
    restricoes_judiciais = db.Column(db.Text, nullable=True)
    observacoes = db.Column(db.Text, nullable=True)  # Added observacoes field
    latitude = db.Column(db.String(20), nullable=True)  # Latitude field
    longitude = db.Column(db.String(20), nullable=True)  # Longitude field
    data_modificacao = db.Column(
        db.DateTime, default=get_current_time_brasilia, onupdate=get_current_time_brasilia)

    def __repr__(self):
        return f'<UserRegistration {self.nome_completo}>'


class Images(db.Model):
    __tablename__ = 'images'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # Foreign key relationship with user_registration.infopen
    infopen = db.Column(db.String(100), db.ForeignKey('user_registration.infopen'), nullable=False)
    # Store Base64 encoded image
    image_b64 = db.Column(db.Text, nullable=False)
    # Optional fields for profile image and image hash
    imagem_perfil = db.Column(db.String(200), nullable=True)  # Added for consistency with old field
    image_hash = db.Column(db.String(64), nullable=True)  # SHA256 hash of the image
    # Optional datetime field
    created_at = db.Column(db.DateTime, default=get_current_time_brasilia)

    def __repr__(self):
        return f'<Images {self.infopen}>'


class Judiciary(db.Model):
    __tablename__ = 'judiciary'
    id = db.Column(db.Integer, primary_key=True)
    infopen = db.Column(db.String(100), db.ForeignKey('user_registration.infopen'), nullable=False)
    data_notificacao = db.Column(db.Date, nullable=True)  # Data da Notificação
    numero_seeu = db.Column(db.String(100), nullable=True)  # Número do SEEU
    protocolo = db.Column(db.String(100), nullable=True)  # Protocolo
    anotacoes = db.Column(db.Text, nullable=True)  # Anotações
    data_registro = db.Column(db.DateTime, default=get_current_time_brasilia, onupdate=get_current_time_brasilia)

    def __repr__(self):
        return f'<Judiciary {self.numero_seeu}>'


# Create tables only if they don't exist
with app.app_context():
    # Check if tables exist, create them if they don't
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()

    if 'images' not in table_names or 'judiciary' not in table_names:  # If images or judiciary table doesn't exist, create all tables
        db.create_all()
    else:
        # Add new columns if they don't exist in user_registration
        from sqlalchemy import text

        # Remove imagem_perfil and image_hash from user_registration table
        # Since SQLite doesn't support DROP COLUMN directly, we'll just not use these columns going forward
        # Add new columns to images table if they don't exist
        result = db.session.execute(text("PRAGMA table_info(images)"))
        columns = [row[1] for row in result.fetchall()]

        if 'imagem_perfil' not in columns:
            db.session.execute(text("ALTER TABLE images ADD COLUMN imagem_perfil VARCHAR(200)"))
        if 'image_hash' not in columns:
            db.session.execute(text("ALTER TABLE images ADD COLUMN image_hash VARCHAR(64)"))

        # Also check user_registration table for any other columns that may need to be added
        result = db.session.execute(text("PRAGMA table_info(user_registration)"))
        columns = [row[1] for row in result.fetchall()]

        if 'latitude' not in columns:
            db.session.execute(
                text("ALTER TABLE user_registration ADD COLUMN latitude VARCHAR(20)"))
        if 'longitude' not in columns:
            db.session.execute(
                text("ALTER TABLE user_registration ADD COLUMN longitude VARCHAR(20)"))
        if 'telefone' not in columns:
            db.session.execute(
                text("ALTER TABLE user_registration ADD COLUMN telefone VARCHAR(20)"))
        if 'observacoes' not in columns:
            db.session.execute(
                text("ALTER TABLE user_registration ADD COLUMN observacoes TEXT"))

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


# SQLAlchemy event listeners to convert text fields to uppercase before insert/update
@event.listens_for(UserRegistration, 'before_insert')
@event.listens_for(UserRegistration, 'before_update')
def uppercase_text_fields(mapper, connection, target):
    # Convert all text fields to uppercase
    if target.infopen:
        target.infopen = target.infopen.upper()
    if target.nome_completo:
        target.nome_completo = target.nome_completo.upper()
    if target.cpf:
        target.cpf = target.cpf.upper()
    if target.telefone:
        target.telefone = target.telefone.upper()
    if target.rua:
        target.rua = target.rua.upper()
    if target.bairro:
        target.bairro = target.bairro.upper()
    if target.numero:
        target.numero = target.numero.upper()
    if target.municipio:
        target.municipio = target.municipio.upper()
    if target.ueop:
        target.ueop = target.ueop.upper()
    if target.cia:
        target.cia = target.cia.upper()
    if target.restricoes_judiciais:
        target.restricoes_judiciais = target.restricoes_judiciais.upper()
    if target.observacoes:
        target.observacoes = target.observacoes.upper()
    if target.latitude:
        target.latitude = target.latitude.upper()
    if target.longitude:
        target.longitude = target.longitude.upper()


@app.route('/')
def index():
    return redirect(url_for('register'))


@app.route('/menu')
def show_menu():
    return render_template('menu.html', active_page='menu')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        infopen = request.form.get('infopen')
        nome_completo = request.form.get('nome_completo')
        cpf = request.form.get('cpf')
        telefone = request.form.get('telefone')
        rua = request.form.get('rua')
        bairro = request.form.get('bairro')
        numero = request.form.get('numero')
        municipio = request.form.get('municipio')
        ueop = request.form.get('ueop')
        cia = request.form.get('cia')
        restricoes_judiciais = request.form.get('restricoes_judiciais')
        observacoes = request.form.get('observacoes')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')

        # Backend validation for infopen field
        if not infopen or not infopen.strip():
            flash('O campo Infopen é obrigatório.', 'error')
            return render_template('register.html', active_page='register', show_institutional_content=False, enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)

        # Check if infopen already exists to ensure uniqueness
        existing_user = UserRegistration.query.filter_by(infopen=infopen).first()
        if existing_user:
            flash('Egresso já cadastrado!', 'error')
            return render_template('register.html', active_page='register', show_institutional_content=False, enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)

        # Handle image upload - convert to Base64 and store in images table
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
                    image_b64=image_b64,
                    imagem_perfil=infopen,  # For consistency
                    image_hash=image_hash
                )
                db.session.add(new_image)

        # Create new user registration
        new_user = UserRegistration(
            infopen=infopen,
            nome_completo=nome_completo,
            cpf=cpf,
            telefone=telefone,
            rua=rua,
            bairro=bairro,
            numero=numero,
            municipio=municipio,
            ueop=ueop,
            cia=cia,
            restricoes_judiciais=restricoes_judiciais,
            observacoes=observacoes,
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
    return render_template('register.html', active_page='register', show_institutional_content=False, enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)


@app.route('/search', methods=['GET', 'POST'])
def search():
    # Get page number from request arguments, default to 1
    page = request.args.get('page', 1, type=int)
    per_page = 50  # Number of records per page

    if request.method == 'POST':
        # Get filter values
        infopen = request.form.get('infopen')
        nome_completo = request.form.get('nome_completo')
        cpf = request.form.get('cpf')
        municipio = request.form.get('municipio')
        ueop = request.form.get('ueop')
        cia = request.form.get('cia')
        data_modificacao = request.form.get('data_modificacao')
        ano_modificacao = request.form.get('ano_modificacao')
        mes_modificacao = request.form.get('mes_modificacao')

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

        # Date filters based on data_modificacao
        if data_modificacao:
            # Parse the date string and filter for that specific date
            from datetime import datetime
            try:
                parsed_date = datetime.strptime(data_modificacao, '%Y-%m-%d').date()
                query = query.filter(db.func.date(UserRegistration.data_modificacao) == parsed_date)
            except ValueError:
                flash('Formato de data inválido. Use AAAA-MM-DD.', 'error')

        if ano_modificacao:
            try:
                ano = int(ano_modificacao)
                query = query.filter(db.extract('year', UserRegistration.data_modificacao) == ano)
            except ValueError:
                flash('Ano inválido. Use formato numérico (ex: 2026).', 'error')

        if mes_modificacao:
            try:
                mes = int(mes_modificacao)
                query = query.filter(db.extract('month', UserRegistration.data_modificacao) == mes)
            except ValueError:
                flash('Mês inválido. Use formato numérico (1-12).', 'error')

        # Paginate the results
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        users = pagination.items

        # For each user, check if they have an associated image
        users_with_images = []
        for user in users:
            image_exists = Images.query.filter_by(infopen=user.infopen).first() if user.infopen else None
            users_with_images.append((user, bool(image_exists)))

        # Prepare enterprise data for the template
        return render_template('search.html', active_page='search', show_institutional_content=False, users=users_with_images, pagination=pagination,
                               enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)
    else:
        # For GET requests (no filters), get all users and check for associated images
        pagination = UserRegistration.query.paginate(page=page, per_page=per_page, error_out=False)
        users = pagination.items

        users_with_images = []
        for user in users:
            image_exists = Images.query.filter_by(infopen=user.infopen).first() if user.infopen else None
            users_with_images.append((user, bool(image_exists)))

        # Prepare enterprise data for the template
        return render_template('search.html', active_page='search', show_institutional_content=False, users=users_with_images, pagination=pagination,
                               enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)


@app.route('/edit/<int:user_id>', methods=['GET', 'POST'])
def edit(user_id):
    user = UserRegistration.query.get_or_404(user_id)
    # Check if user has an associated image
    image_exists = Images.query.filter_by(infopen=user.infopen).first() if user.infopen else None

    if request.method == 'POST':
        # Update user data
        infopen = request.form.get('infopen')

        # Backend validation for infopen field
        if not infopen or not infopen.strip():
            flash('O campo Infopen é obrigatório.', 'error')
            return render_template('edit.html', active_page='register', show_institutional_content=False, user=user, image_exists=image_exists, enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)

        # Check if infopen already exists for a different user (avoiding self-conflict)
        existing_user = UserRegistration.query.filter(
            UserRegistration.infopen == infopen,
            UserRegistration.id != user_id  # Exclude current user from check
        ).first()
        if existing_user:
            flash('Egresso já cadastrado!', 'error')
            return render_template('edit.html', active_page='register', show_institutional_content=False, user=user, image_exists=image_exists, enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)

        user.infopen = infopen
        user.nome_completo = request.form.get('nome_completo')
        user.cpf = request.form.get('cpf')
        user.telefone = request.form.get('telefone')
        user.rua = request.form.get('rua')
        user.bairro = request.form.get('bairro')
        user.numero = request.form.get('numero')
        user.municipio = request.form.get('municipio')
        user.ueop = request.form.get('ueop')
        user.cia = request.form.get('cia')
        user.restricoes_judiciais = request.form.get('restricoes_judiciais')
        user.observacoes = request.form.get('observacoes')
        user.latitude = request.form.get('latitude')
        user.longitude = request.form.get('longitude')

        # Handle image upload - convert to Base64 and store in images table
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
                    infopen=user.infopen).first()
                if existing_image:
                    db.session.delete(existing_image)

                # Create new image record
                new_image = Images(
                    infopen=user.infopen,
                    image_b64=image_b64,
                    imagem_perfil=user.infopen,  # For consistency
                    image_hash=image_hash
                )
                db.session.add(new_image)

        try:
            db.session.commit()
            flash('Registro atualizado com sucesso!', 'success')
            return redirect(url_for('search'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar o registro: {str(e)}', 'error')

    return render_template('edit.html', active_page='register', show_institutional_content=False, user=user, image_exists=image_exists, enterprise_data=ENTERPRISE_DATA, municipalities=MUNICIPALITIES)

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


@app.route('/seeu', methods=['GET', 'POST'])
def seeu():
    # Get infopen from URL parameters for pre-selecting in the dropdown
    selected_infopen = request.args.get('infopen', '')

    # Handle POST request for creating a new judiciary record
    # We check for a field unique to the creation form, like 'protocolo',
    # to distinguish it from a filter POST.
    if request.method == 'POST' and 'protocolo' in request.form:
        infopen = request.form.get('infopen')
        data_notificacao = request.form.get('data_notificacao')
        numero_seeu = request.form.get('numero_seeu')
        protocolo = request.form.get('protocolo')
        anotacoes = request.form.get('anotacoes')

        if not infopen:
            flash('O campo Infopen é obrigatório para criar um registro.', 'error')
        else:
            data_notificacao_obj = None
            if data_notificacao:
                try:
                    data_notificacao_obj = datetime.strptime(
                        data_notificacao, '%Y-%m-%d').date()
                except ValueError:
                    flash('Formato de data inválido. Use AAAA-MM-DD.', 'error')
                    # To prevent incorrect data display, we redirect and allow the filter logic below to run
                    return redirect(url_for('seeu', **request.form))

            new_record = Judiciary(
                infopen=infopen,
                data_notificacao=data_notificacao_obj,
                numero_seeu=numero_seeu,
                protocolo=protocolo,
                anotacoes=anotacoes
            )

            try:
                db.session.add(new_record)
                db.session.commit()
                flash('Registro judicial salvo com sucesso!', 'success')
                return redirect(url_for('seeu'))
            except Exception as e:
                db.session.rollback()
                flash(
                    f'Erro ao salvar o registro judicial: {str(e)}', 'error')

    # --- Filtering and Display Logic (for GET and POST-based filters) ---

    # Use request.values to get parameters from both GET and POST
    filter_infopen = request.values.get('filter_infopen', '').strip()
    filter_nome = request.values.get('filter_nome', '').strip()
    filter_numero_seeu = request.values.get('filter_numero_seeu', '').strip()

    # Start with a base query on the Judiciary table
    query = Judiciary.query

    # Conditionally join with UserRegistration only if filtering by name
    if filter_nome:
        query = query.join(
            UserRegistration, Judiciary.infopen == UserRegistration.infopen)
        query = query.filter(
            UserRegistration.nome_completo.ilike(f'%{filter_nome}%'))

    # Apply infopen filter if provided
    if filter_infopen:
        query = query.filter(Judiciary.infopen.ilike(f'%{filter_infopen}%'))

    # Apply numero_seeu filter if provided
    if filter_numero_seeu:
        query = query.filter(Judiciary.numero_seeu.ilike(f'%{filter_numero_seeu}%'))

    # Execute the final query
    judiciary_records = query.order_by(Judiciary.data_registro.desc()).all()

    # Get all users for the registration dropdown
    users = UserRegistration.query.order_by(
        UserRegistration.nome_completo).all()

    return render_template(
        'seeu.html',
        active_page='seeu',
        show_institutional_content=False,
        show_institutional_text=False,
        users=users,
        judiciary_records=judiciary_records,
        selected_infopen=selected_infopen,
        # Pass filter values back to template to keep them in the form
        filter_infopen=filter_infopen,
        filter_nome=filter_nome,
        filter_numero_seeu=filter_numero_seeu
    )


@app.route('/edit_seeu/<int:record_id>', methods=['GET', 'POST'])
def edit_seeu(record_id):
    record = Judiciary.query.get_or_404(record_id)

    if request.method == 'POST':
        # Update record data
        infopen = request.form.get('infopen')
        data_notificacao = request.form.get('data_notificacao')
        numero_seeu = request.form.get('numero_seeu')
        protocolo = request.form.get('protocolo')
        anotacoes = request.form.get('anotacoes')

        # Validate required fields
        if not infopen:
            flash('O campo Infopen é obrigatório.', 'error')
            users = UserRegistration.query.all()
            return render_template('edit_seeu.html', active_page='seeu', show_institutional_content=False, record=record, users=users)

        # Convert date string to date object if provided
        from datetime import datetime
        data_notificacao_obj = None
        if data_notificacao:
            try:
                data_notificacao_obj = datetime.strptime(data_notificacao, '%Y-%m-%d').date()
            except ValueError:
                flash('Formato de data inválido. Use AAAA-MM-DD.', 'error')
                users = UserRegistration.query.all()
                return render_template('edit_seeu.html', active_page='seeu', show_institutional_content=False, record=record, users=users)

        record.infopen = infopen
        record.data_notificacao = data_notificacao_obj
        record.numero_seeu = numero_seeu
        record.protocolo = protocolo
        record.anotacoes = anotacoes

        try:
            db.session.commit()
            flash('Registro judicial atualizado com sucesso!', 'success')
            return redirect(url_for('seeu'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar o registro judicial: {str(e)}', 'error')

    users = UserRegistration.query.all()
    return render_template('edit_seeu.html', active_page='seeu', show_institutional_content=False, record=record, users=users)


@app.route('/delete_seeu/<int:record_id>', methods=['POST'])
def delete_seeu(record_id):
    record = Judiciary.query.get_or_404(record_id)

    try:
        # Delete the judiciary record from the database
        db.session.delete(record)
        db.session.commit()
        flash('Registro judicial excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir o registro judicial: {str(e)}', 'error')

    return redirect(url_for('seeu'))


@app.route('/export_csv', methods=['POST'])
def export_csv():
    # Get filter values from the form (same as in search route)
    infopen = request.form.get('infopen')
    nome_completo = request.form.get('nome_completo')
    cpf = request.form.get('cpf')
    municipio = request.form.get('municipio')
    ueop = request.form.get('ueop')
    cia = request.form.get('cia')
    data_modificacao = request.form.get('data_modificacao')
    ano_modificacao = request.form.get('ano_modificacao')
    mes_modificacao = request.form.get('mes_modificacao')

    # Build query with filters, joining with images table
    query = db.session.query(UserRegistration, Images.image_b64).outerjoin(
        Images, UserRegistration.infopen == Images.infopen
    )

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

    # Date filters based on data_modificacao
    if data_modificacao:
        # Parse the date string and filter for that specific date
        from datetime import datetime
        try:
            parsed_date = datetime.strptime(data_modificacao, '%Y-%m-%d').date()
            query = query.filter(db.func.date(UserRegistration.data_modificacao) == parsed_date)
        except ValueError:
            flash('Formato de data inválido. Use AAAA-MM-DD.', 'error')

    if ano_modificacao:
        try:
            ano = int(ano_modificacao)
            query = query.filter(db.extract('year', UserRegistration.data_modificacao) == ano)
        except ValueError:
            flash('Ano inválido. Use formato numérico (ex: 2026).', 'error')

    if mes_modificacao:
        try:
            mes = int(mes_modificacao)
            query = query.filter(db.extract('month', UserRegistration.data_modificacao) == mes)
        except ValueError:
            flash('Mês inválido. Use formato numérico (1-12).', 'error')

    results = query.all()

    # Generate CSV content with UTF-8 BOM encoding
    import csv
    import io
    from flask import make_response

    # Create a string buffer
    output = io.StringIO()

    # Write header
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Infopen', 'Nome Completo', 'CPF', 'Telefone', 'Rua', 'Bairro',
        'Número', 'Município', 'UEOP', 'CIA', 'Restrições Judiciais',
        'Observações', 'Latitude', 'Longitude', 'Data de Modificação', 'Imagem Base64'
    ])

    # Write data rows
    for user, image_b64 in results:
        writer.writerow([
            user.id,
            user.infopen or '',
            user.nome_completo or '',
            user.cpf or '',
            user.telefone or '',
            user.rua or '',
            user.bairro or '',
            user.numero or '',
            user.municipio or '',
            user.ueop or '',
            user.cia or '',
            user.restricoes_judiciais or '',
            user.observacoes or '',
            user.latitude or '',
            user.longitude or '',
            user.data_modificacao.strftime(
                '%d/%m/%Y %H:%M:%S') if user.data_modificacao else '',
            image_b64 or ''  # Include image_b64, empty if not available
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


@app.route('/export_seeu_csv', methods=['GET'])
def export_seeu_csv():
    # Get filter parameters from the URL (same as in seeu route)
    filter_infopen = request.args.get('filter_infopen', '').strip()
    filter_nome = request.args.get('filter_nome', '').strip()
    filter_numero_seeu = request.args.get('filter_numero_seeu', '').strip()

    # Start with a base query on the Judiciary table
    query = Judiciary.query

    # Conditionally join with UserRegistration only if filtering by name
    if filter_nome:
        query = query.join(
            UserRegistration, Judiciary.infopen == UserRegistration.infopen)
        query = query.filter(
            UserRegistration.nome_completo.ilike(f'%{filter_nome}%'))

    # Apply infopen filter if provided
    if filter_infopen:
        query = query.filter(Judiciary.infopen.ilike(f'%{filter_infopen}%'))

    # Apply numero_seeu filter if provided
    if filter_numero_seeu:
        query = query.filter(Judiciary.numero_seeu.ilike(f'%{filter_numero_seeu}%'))

    # Execute the final query
    judiciary_records = query.order_by(Judiciary.data_registro.desc()).all()

    # Generate CSV content with UTF-8 BOM encoding
    import csv
    import io
    from flask import make_response

    # Create a string buffer
    output = io.StringIO()

    # Write header - match the visible columns in the seeu table
    writer = csv.writer(output)
    writer.writerow([
        'Infopen', 'Nome', 'Data da Notificação', 'Número do SEEU',
        'Protocolo', 'Anotações', 'Data do Registro'
    ])

    # Write data rows
    for record in judiciary_records:
        # Get the associated user to get the name
        user = UserRegistration.query.filter_by(infopen=record.infopen).first()

        writer.writerow([
            record.infopen or '',
            user.nome_completo if user else '',
            record.data_notificacao.strftime('%d/%m/%Y') if record.data_notificacao else '',
            record.numero_seeu or '',
            record.protocolo or '',
            record.anotacoes or '',
            record.data_registro.strftime('%d/%m/%Y %H:%M:%S') if record.data_registro else ''
        ])

    # Get the CSV content as string
    csv_content = output.getvalue()
    output.close()

    # Add UTF-8 BOM to the content
    csv_content_with_bom = '\ufeff' + csv_content

    # Create response with CSV content
    response = make_response(csv_content_with_bom)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=registros_seeu_exportados.csv'

    return response


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)


