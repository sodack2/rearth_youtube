import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'

# ✅ Railwayの環境変数 DATABASE_URL を使う
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    videos = db.relationship('Video', backref='user', lazy=True)
    comments = db.relationship('Comment', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    filename = db.Column(db.String(200))
    thumbnail = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    view_count = db.Column(db.Integer, default=0)
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    comments = db.relationship('Comment', backref='video', lazy=True)

class Thread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    categories = Category.query.all()
    return render_template('index.html', categories=categories)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    categories = Category.query.all()
    if request.method == 'POST':
        title = request.form['title']
        category_id = request.form['category']
        file = request.files['file']
        thumbnail = request.files.get('thumbnail')

        if not thumbnail or not thumbnail.filename:
            flash('サムネイル画像は必須です！')
            return redirect(url_for('upload'))

        category = Category.query.get(category_id)
        category_name = category.name

        genre_folder = os.path.join(app.config['UPLOAD_FOLDER'], category_name)
        os.makedirs(genre_folder, exist_ok=True)
        filename = file.filename
        filepath = os.path.join(genre_folder, filename)
        file.save(filepath)

        thumbnail_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnails')
        os.makedirs(thumbnail_folder, exist_ok=True)

        thumb_name = f"{filename}_thumb.jpg"
        thumb_path = os.path.join(thumbnail_folder, thumb_name)
        thumbnail.save(thumb_path)

        video = Video(
            title=title,
            filename=f"{category_name}/{filename}",
            thumbnail=f"thumbnails/{thumb_name}",
            category_id=category_id,
            user_id=current_user.id
        )
        db.session.add(video)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('upload.html', categories=categories)

@app.route('/uploads/<path:filepath>')
def uploaded_file(filepath):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filepath)

@app.route('/genre/<int:category_id>')
def genre(category_id):
    category = Category.query.get_or_404(category_id)
    videos = Video.query.filter_by(category_id=category_id).all()
    threads = Thread.query.filter_by(category_id=category_id).all()
    return render_template('genre.html', category=category, videos=videos, threads=threads)

@app.route('/create_thread/<int:category_id>', methods=['POST'])
@login_required
def create_thread(category_id):
    title = request.form['title']
    new_thread = Thread(title=title, category_id=category_id)
    db.session.add(new_thread)
    db.session.commit()
    return redirect(url_for('genre', category_id=category_id))

@app.route('/video/<int:video_id>', methods=['GET', 'POST'])
def video_page(video_id):
    video = Video.query.get_or_404(video_id)
    video.view_count += 1

    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('コメントを投稿するにはログインしてください。')
            return redirect(url_for('login', next=request.path))
        content = request.form.get('content')
        if content:
            new_comment = Comment(content=content, video=video, user=current_user)
            db.session.add(new_comment)
            db.session.commit()
            return redirect(url_for('video_page', video_id=video.id))
    else:
        db.session.commit()

    next_video = Video.query.filter(Video.id > video.id).order_by(Video.id.asc()).first()
    return render_template('video.html', video=video, next_video=next_video)

@app.route('/admin/delete_comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    if not current_user.is_admin:
        abort(403)

    comment = Comment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/admin/delete_video/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    if not current_user.is_admin:
        abort(403)

    video = Video.query.get_or_404(video_id)
    db.session.delete(video)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return "Username already exists"
        user = User(username=username)
        user.set_password(password)
        if username == 'sota':
            user.is_admin = True  # ✅ sotaだけ管理者
        else:
            user.is_admin = False
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            return "Invalid credentials"
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

with app.app_context():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    db.create_all()
    if not Category.query.first():
        db.session.add_all([
            Category(name='Life'),
            Category(name='War')
        ])
        db.session.commit()

    # ✅ sotaがいなければ作る
    admin_user = User.query.filter_by(username='sota').first()
    if not admin_user:
        admin = User(username='sota', is_admin=True)
        admin.set_password('sotapassword')  # 任意の初期パス
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
