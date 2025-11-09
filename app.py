import os, json
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_dance.contrib.google import make_google_blueprint, google
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(150), unique=True)
    tokens = db.Column(db.Integer, default=100)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

blueprint = make_google_blueprint(
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    redirect_url="/auth/callback",
    scope=["profile", "email"]
)
app.register_blueprint(blueprint, url_prefix="/login")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/auth/callback")
def auth_callback():
    if not google.authorized:
        return redirect(url_for("google.login"))
    resp = google.get("/oauth2/v2/userinfo")
    info = resp.json()
    email = info["email"]
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(name=info["name"], email=email, tokens=100)
        db.session.add(user)
        db.session.commit()
    login_user(user)
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("index.html")

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.route("/generate", methods=["POST"])
@login_required
def generate():
    notes = request.form.get("notes", "")
    num_questions = int(request.form.get("num_questions", 10))
    user = current_user
    if user.tokens < num_questions:
        return render_template("index.html", quiz={"title": "Error", "content": "Not enough tokens!"})
    try:
        prompt = f"Generate {num_questions} unique quiz questions with answers based on these notes:\n{notes}"
        model = genai.GenerativeModel(MODEL)
        response = model.generate_content(prompt)
        quiz_text = response.text
    except Exception as e:
        quiz_text = f"Error generating quiz: {e}"
    user.tokens -= num_questions
    db.session.commit()
    return render_template("index.html", quiz={"title": "Generated Quiz", "content": quiz_text})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
