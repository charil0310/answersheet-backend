from flask import Flask
from config import Config
from extensions import db, migrate, jwt  # 👈 加上 jwt
from flask_cors import CORS 
from routes.auth import auth_bp
from routes.class_route import class_bp
from routes.student_route import student_bp
from routes.exam_route import exam_bp
from routes.sheet_route import sheet_bp
from routes.stats_route import stats_bp
from routes.export_route import export_bp
from flasgger import Swagger

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 初始化扩展
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)   # 👈 必须加
    CORS(app)
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec_1",
                "route": "/apispec_1.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/apidocs/",
    }

    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "Answer Sheet API",
            "description": "答题卡批改系统接口文档",
            "version": "1.0"
        },
        "securityDefinitions": {
            "Bearer": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "输入: Bearer <你的JWT>"
            }
        },
        "security": [
            {
                "Bearer": []
            }
        ]
    }

    Swagger(app, config=swagger_config, template=swagger_template)
    # 注册蓝图
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(class_bp, url_prefix="/api/class")
    app.register_blueprint(student_bp, url_prefix="/api/student")
    app.register_blueprint(exam_bp, url_prefix="/api/exam")
    app.register_blueprint(sheet_bp, url_prefix="/api/sheet")
    app.register_blueprint(stats_bp, url_prefix="/api/stats")
    app.register_blueprint(export_bp, url_prefix="/api/export")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)