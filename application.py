import os

from flask import Flask, session, render_template, request, redirect, url_for, flash, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
import requests
import json

app = Flask(__name__)
app.secret_key = b'\xda\x1e^\x92\n\xed\xd0A\xb5\xe01\xf3\x8aQ\xcf\xbf'

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

# Keys in DB
bookkeys   = ["book_id", "isbn", "title", "author", "year"]

#-------------------------------------------------------------------------------
# ROUTES
# INDEX
@app.route("/")
def index():
    if 'user' in session:
        return redirect( url_for('profile') )
    else:
        return render_template("login.html")


# ------------------------------------------------------------------------------
# AUTHENTICATION
@app.route("/register", methods=["POST", "GET"])
def register():
    if request.method == "POST":
    # Catch username from the form
        username = request.form.get("new_username")
        password = request.form.get("new_password")
        email    = request.form.get("email")
        knowns = db.execute("SELECT username, email FROM users").fetchall()
        db.commit()

        # Check the form is filled correctly
        if not username or not password:
            flash("Please fill in all fields")
            return render_template("register.html")

        # Check email and username will be unique
        elif username in [i[0] for i in knowns] or email in [i[1] for i in knowns]:
            flash("Username or email already exists.")
            return render_template("register.html")
        else:
            # Add new user
            db.execute("INSERT INTO users (username, password, email) VALUES (:username, :password, :email);",
                       {"username" : username, "password" : password, "email" : email})
            db.commit()

        return redirect(url_for("login"))

    else:
        return render_template("register.html")

@app.route("/login", methods = ["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")
        username = request.form.get("username")
        stored_password, user_id = db.execute("SELECT password, id FROM users WHERE username = :username",
                                             {"username" : username}).first()
        db.commit()

        if password == stored_password:
            session["user"] = {"name" : username, "id" : user_id}
            return redirect(url_for("profile"))

        else:
            flash('Please check your login details and try again.')
            return render_template("login.html")

    else:
        if "user" in session:
            return redirect(url_for("profile"))
        else:
            return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    print(session)
    return redirect(url_for("index"))


# ------------------------------------------------------------------------------
# USER PROFILE
@app.route("/profile", methods = ["POST", "GET"])
def profile():
    if "user" in session:
        # get user id and and name from session
        user_id  = session["user"]["id"]
        username = session["user"]["name"]

        # get the ids of the boks they reviewed
        book_ids_result = db.execute("SELECT book_id FROM reviews WHERE user_id = :user_id ORDER BY book_id",
                                    {"user_id" : user_id}).fetchall()
        db.commit()
        book_ids = tuple([i for row in book_ids_result for i in row])
        if len(book_ids) > 0:
            # get the title and author of those books
            bookinfos_result = db.execute("SELECT title, author, id FROM books WHERE id IN :book_ids",
                                              {"book_ids" : book_ids}).fetchall()
            bookinfos = [{"title" : row[0], "author" : row[1], "book_id" : row[2]} for row in bookinfos_result]

            # get the text and rating of the reviews they wrote
            reviews_results = db.execute("SELECT text, rating, id, book_id FROM reviews WHERE user_id = :user_id ORDER BY book_id",
                       {"user_id" : user_id}).fetchall()
            reviews = [{"text" : row[0], "rating" : row[1], "id" : row[2]} for row in reviews_results]

            # pass title-text pairs as entries
            entries = [{"review" : review, "bookinfo" : bookinfo} for review, bookinfo in zip(reviews, bookinfos)]
            db.commit()
            return render_template("profile.html", username = username, entries = entries)
        else:
            return render_template("profile.html", username = username)
    else:
        flash("You must be logged in to see your profile!")
        return render_template("login.html")


# ------------------------------------------------------------------------------
# BOOKS INTERFACE
@app.route("/find_book", methods = ["POST", "GET"])
def find_book():
    if request.method == "POST":
        query = request.form.get("query").replace("'", "").replace(" ", ".*")
        sql = "SELECT id, title, author, isbn FROM books WHERE (title ~* '{}') OR (author ~* '{}') OR (isbn ~* '{}')"
        sqlfilled = sql.format(query, query, query)
        results = db.execute(sqlfilled).fetchall()
        db.commit()
        if len(results) > 0:
            return render_template("book_results.html", books = results)
        else:
            flash("No matches for '{}'. Please try again.".format(query))
            return render_template("find_book.html")


    else:
        return render_template("find_book.html")

@app.route("/book_page/<book_id>", methods = ["GET"])
def book_page(book_id):
    bookinfo = db.execute("SELECT * FROM books WHERE id = :book_id",
                         {"book_id" : book_id}).fetchone()
    bookinfo = {key : val for key, val in zip(bookkeys, bookinfo)}

    if "user" in session:
        user_id = session['user']['id']
        user_review = db.execute("SELECT * FROM reviews WHERE book_id = :book_id AND user_id = :user_id",
                                {"book_id" : book_id, "user_id" : user_id}).fetchone()
    else:
        user_review = None

    others_reviews = db.execute("SELECT * FROM reviews WHERE book_id = :book_id",
                               {"book_id" : book_id}).fetchall()
    if len(others_reviews) > 0:
        others_reviews = [{"id" : val[0], "book_id" : val[1], "user_id" : val[2], "rating" : val[3], "text" : val[4]} for val in  others_reviews]
    else:
        others_reviews = None

    # Ratings from Goodreads
    url_ratings = "https://www.goodreads.com/book/review_counts.json"
    rating = requests.get(url_ratings, params = {"key" : "K4k2ivUsWUJWOAb3RLV8Q", "isbns" : bookinfo["isbn"]})
    avg_rating    = rating.json()["books"][0]["average_rating"]
    rating_counts = rating.json()["books"][0]["work_ratings_count"]

    # Goodreads bookid for linkout
    url_book = "https://www.goodreads.com/book/isbn_to_id/"
    gr_book = requests.get(url_book, params = {"key" : "K4k2ivUsWUJWOAb3RLV8Q", "isbn" : bookinfo["isbn"]})
    gr_id  = gr_book.json()

    return render_template('book_page.html', bookinfo = bookinfo,
                           user_review = user_review,
                           others_reviews = others_reviews,
                           avg_rating = avg_rating,
                           rating_counts = rating_counts,
                           gr_id = gr_id)


# ------------------------------------------------------------------------------
# REVIEWS WRITING AND EDITING
@app.route("/review_write/<book_id>", methods = ["GET"])
def review_write(book_id):
    if "user" in session:
        bookinfo = db.execute("SELECT * FROM books WHERE id = :book_id",
                             {"book_id" : book_id}).fetchone()
        book = {key : val for key, val in zip(bookkeys, bookinfo)}
        return render_template("review_write.html", book = book)
    else:
        flash("Log in to write a review")
        return redirect(url_for('login'))

@app.route("/review_post/<book_id>", methods = ["POST"])
def review_post(book_id):
    text = request.form.get("text")
    rating = request.form.get("rating")
    db.execute("INSERT INTO reviews (book_id, user_id, rating, text) VALUES (:book_id, :user_id, :rating, :text)",
               {"book_id" : book_id, "text" : text, "user_id" : session["user"]["id"], "rating" : rating})
    db.commit()
    return redirect(url_for("profile"))


@app.route("/edit/<review_id>", methods = ["GET"])
def edit(review_id):
    # fetch current text
    review_text = db.execute("SELECT text FROM reviews WHERE id = :review_id",
                            {"review_id" : review_id}).fetchone()[0]
    book_title, book_author = db.execute("SELECT title, author FROM books WHERE id = (SELECT book_id FROM reviews WHERE id = :review_id)",
                                        {"review_id" : review_id}).fetchone()
    db.commit()
    return render_template("edit.html", review_text = review_text,
                            book_title = book_title, review_id = review_id,
                            book_author = book_author)

@app.route("/review_update/<review_id>", methods = ["POST"])
def review_update(review_id):
    new_text = request.form.get("new_text")
    db.execute("UPDATE reviews SET text = :new_text WHERE id = :review_id",
              {"new_text" : new_text, "review_id" : review_id})
    db.commit()
    return redirect(url_for("profile"))


#-------------------------------------------------------------------------------
# API ROUTES
@app.route("/api/books/<string:isbn>")
def book_api(isbn):
    """Return details about book listed in my database"""

    book = db.execute("SELECT * FROM books WHERE isbn = :isbn",
                     {"isbn" : isbn}).fetchone()

    if not book:
        return jsonify({"error" : "isbn not in database"}), 404
    else:
        book_data = {key : val for key, val in zip(bookkeys, book)}
        return jsonify(book_data)
