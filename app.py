from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lostandfound.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

db = SQLAlchemy(app)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_type = db.Column(db.String(10), nullable=False)  # 'lost' or 'found'
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    contact = db.Column(db.String(100), nullable=False)
    image = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('posts', lazy=True))

# Initialize database
with app.app_context():
    db.create_all()
    # Create default admin if doesn't exist
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@lostandfound.com',
            password=generate_password_hash('admin123'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()

# Routes
@app.route('/')
def index():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('index.html', posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            flash('Login successful!', 'success')
            
            if user.is_admin:
                return redirect(url_for('admin_panel'))
            return redirect(url_for('index'))
        
        flash('Invalid username or password!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/chat')
def chat():
    """Render the chatbot interface."""
    return render_template('chat.html')


def _generate_chat_reply(user_message: str) -> str:
    message = (user_message or '').strip().lower()

    if not message:
        return "Please type something 😊"

    # Greeting
    if "hello" in message or "hi" in message:
        return "Hello! 👋 I am your Lost & Found assistant. How can I help?"

    # How to post
    if "lost" in message and "how" in message:
        return "To report a lost item: Login → Click 'New Post' → Fill details → Submit."

    if "found" in message and "how" in message:
        return "To report a found item: Login → Click 'New Post' → Select 'Found' → Submit."

    # Add post
    if "post" in message or "add" in message:
        return "Click on 'New Post' in the menu to add lost/found items."

    # Auth help
    if "login" in message:
        return "Go to login page and enter your username and password."

    if "register" in message:
        return "Click Register and create your account."

    # Count items
    if "lost" in message:
        count = Post.query.filter_by(post_type='lost').count()
        return f"There are {count} lost items available. Check homepage."

    if "found" in message:
        count = Post.query.filter_by(post_type='found').count()
        return f"There are {count} found items available."

    # Recent posts
    if "recent" in message or "latest" in message:
        posts = Post.query.order_by(Post.created_at.desc()).limit(3).all()
        if not posts:
            return "No posts yet."

        reply = "Latest posts:\n"
        for p in posts:
            reply += f"- {p.title} ({p.post_type})\n"
        return reply

    # Help
    if "help" in message:
        return "Try: lost items, found items, how to post, login, register."

    return "I didn't understand 🤔 Try: 'lost items' or 'how to post'"


@app.route('/chat/api', methods=['POST'])
def chat_api():
    """Simple JSON API for the chatbot."""
    data = request.get_json(force=True, silent=True) or {}
    message = data.get('message', '')
    reply = _generate_chat_reply(message)
    return {"reply": reply}


@app.route('/post/new', methods=['GET', 'POST'])
def new_post():
    if 'user_id' not in session:
        flash('Please login to create a post!', 'warning')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        post_type = request.form.get('post_type')
        title = request.form.get('title')
        description = request.form.get('description')
        location = request.form.get('location')
        contact = request.form.get('contact')
        
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                image_filename = timestamp + filename
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        
        post = Post(
            post_type=post_type,
            title=title,
            description=description,
            location=location,
            contact=contact,
            image=image_filename,
            user_id=session['user_id']
        )
        db.session.add(post)
        db.session.commit()
        
        flash('Post created successfully!', 'success')
        return redirect(url_for('index'))
    
    return render_template('new_post.html')

@app.route('/post/<int:post_id>')
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('view_post.html', post=post)

@app.route('/admin')
def admin_panel():
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Access denied! Admin only.', 'danger')
        return redirect(url_for('index'))
    
    posts = Post.query.order_by(Post.created_at.desc()).all()
    users = User.query.all()
    return render_template('admin.html', posts=posts, users=users)

@app.route('/admin/post/edit/<int:post_id>', methods=['GET', 'POST'])
def edit_post(post_id):
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Access denied!', 'danger')
        return redirect(url_for('index'))
    
    post = Post.query.get_or_404(post_id)
    
    if request.method == 'POST':
        post.title = request.form.get('title')
        post.description = request.form.get('description')
        post.location = request.form.get('location')
        post.contact = request.form.get('contact')
        post.post_type = request.form.get('post_type')
        
        db.session.commit()
        flash('Post updated successfully!', 'success')
        return redirect(url_for('admin_panel'))
    
    return render_template('edit_post.html', post=post)

@app.route('/admin/post/delete/<int:post_id>')
def delete_post(post_id):
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Access denied!', 'danger')
        return redirect(url_for('index'))
    
    post = Post.query.get_or_404(post_id)
    
    # Delete image file if exists
    if post.image:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], post.image)
        if os.path.exists(image_path):
            os.remove(image_path)
    
    db.session.delete(post)
    db.session.commit()
    
    flash('Post deleted successfully!', 'success')
    return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    app.run(debug=True)