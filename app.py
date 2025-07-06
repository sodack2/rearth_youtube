import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SECRET_KEY'] = 'supersecretkey'

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --------------------
# モデル
# --------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(200))

    followers = db.relationship(
        'Follow',
        foreign_keys='Follow.followed_id',
        backref='followed',
        lazy='dynamic'
    )
    following = db.relationship(
        'Follow',
        foreign_keys='Follow.follower_id',
        backref='follower',
        lazy='dynamic'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    filename = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Thread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('thread.id'))
    content = db.Column(db.Text)

# --------------------
# ログインマネージャ
# --------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --------------------
# ルート
# --------------------
@app.route('/')
def index():
    categories = Category.query.all()
    users = User.query.all()
    return render_template('index.html', categories=categories, users=users)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    categories = Category.query.all()
    if request.method == 'POST':
        title = request.form['title']
        category_id = request.form['category']
        file = request.files['file']

        filename = file.filename
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        video = Video(title=title, filename=filename, category_id=category_id, user_id=current_user.id)
        db.session.add(video)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('upload.html', categories=categories)

@app.route('/genre/<int:category_id>')
def genre(category_id):
    category = Category.query.get(category_id)
    videos = Video.query.filter_by(category_id=category_id).all()
    threads = Thread.query.filter_by(category_id=category_id).all()
    return render_template('genre.html', category=category, videos=videos, threads=threads)

@app.route('/thread/<int:thread_id>', methods=['GET', 'POST'])
def thread(thread_id):
    thread = Thread.query.get(thread_id)
    posts = Post.query.filter_by(thread_id=thread_id).all()
    if request.method == 'POST':
        content = request.form['content']
        post = Post(thread_id=thread_id, content=content)
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('thread', thread_id=thread_id))
    return render_template('thread.html', thread=thread, posts=posts)

@app.route('/create_thread/<int:category_id>', methods=['POST'])
@login_required
def create_thread(category_id):
    title = request.form['title']
    new_thread = Thread(title=title, category_id=category_id)
    db.session.add(new_thread)
    db.session.commit()
    return redirect(url_for('genre', category_id=category_id))

# --------------------
# 登録・ログイン・ログアウト
# --------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return "Username already exists"
        user = User(username=username)
        user.set_password(password)
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

# --------------------
# フォロー
# --------------------
@app.route('/follow/<int:user_id>')
@login_required
def follow(user_id):
    user_to_follow = User.query.get(user_id)
    if not user_to_follow:
        return "User not found"
    if current_user.id == user_id:
        return "You can't follow yourself"
    existing = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
    if existing:
        return "Already following"
    follow = Follow(follower_id=current_user.id, followed_id=user_id)
    db.session.add(follow)
    db.session.commit()
    return redirect(url_for('index'))

# --------------------
# 起動
# --------------------
if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    db.create_all()
    if not Category.query.first():
        db.session.add_all([Category(name='Life'), Category(name='War')])
        db.session.commit()
    app.run(debug=True)
