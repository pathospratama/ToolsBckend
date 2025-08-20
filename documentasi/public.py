from flask import Blueprint

doc_bp = Blueprint('documentasi_tools', __name__)
@doc_bp.route("/", methods=["GET"])
def get_data():
    return{"data": "BACKEND TOOLS Ageelio READY"}