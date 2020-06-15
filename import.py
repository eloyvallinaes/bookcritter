#!/usr/bin/python

# Set up SQL database for books project

import csv
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

def create_users():
    pass

def create_books():
    f = open("books.csv")
    reader = csv.reader(f)
    next(reader)
    for isbn, title, author, year in reader:
        db.execute("INSERT INTO books (isbn, title, author, year) VALUES (:isbn, :title, :author, :year)",
                   {"isbn": isbn, "title": title, "author": author, "year" :year})
        print(f"Added book {title}.")
    db.commit()

def create_reviews():
    pass

def main():
    create_reviews()
    create_books()
    create_users()


if __name__ == "__main__":
    main()
