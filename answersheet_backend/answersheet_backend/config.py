import os

class Config:
    SECRET_KEY = "dev"
    JWT_SECRET_KEY = "super-secret-key"
    SQLALCHEMY_DATABASE_URI = "mysql+pymysql://root:Mysql123@localhost/answersheet"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = "uploads"
    RESULT_FOLDER = "output"

    MAX_CONTENT_LENGTH = 20 * 1024 * 1024