from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import pytz  # ✅ 한국 시간 변환 추가
import os
from model.model import analyze_acne_by_parts_result  # YOLO 모델

# Flask 앱 생성
app = Flask(__name__)
app.secret_key = "your_secret_key"  # ✅ 세션 사용을 위한 secret_key 설정

# 업로드 폴더 설정
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# SQLite 데이터베이스 설정
DATABASE_URL = "sqlite:///acne_analysis.db"
engine = create_engine(DATABASE_URL, echo=True)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

# ✅ 한국 시간대 설정
KST = pytz.timezone('Asia/Seoul')

# 데이터베이스 테이블 정의
class AcneAnalysis(Base):
    __tablename__ = "acne_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)  # ✅ UTC → KST 적용 예정
    total_acne_count = Column(Integer, nullable=False)
    max_acne_part = Column(String, nullable=False)
    cause_organ = Column(String, nullable=False)

Base.metadata.drop_all(engine)  # 기존 테이블 삭제
Base.metadata.create_all(engine)  # 데이터베이스 테이블 생성

# ✅ 1️⃣ 첫 화면 (page1.html) → 3초 후 index.html 자동 이동
@app.route("/")
def page1():
    return render_template("page1.html")

# ✅ 2️⃣ 3초 후 이동할 홈 화면 (index.html)
@app.route("/home")
def index():
    return render_template("index.html")

# ✅ 3️⃣ 분석 결과 저장 함수 (한국 시간 적용)
def add_acne_analysis(total_acne_count, max_acne_part):
    session_db = SessionLocal()
    ACNE_CAUSE_MAPPING = {
        "이마": "스트레스",
        "코": "비장",
        "왼쪽볼": "간",
        "오른쪽볼": "폐",
        "턱": "신장"
    }
    cause_organ = ACNE_CAUSE_MAPPING.get(max_acne_part, "알 수 없음")

    # ✅ 한국 시간으로 저장
    uploaded_at = datetime.now(KST)

    new_entry = AcneAnalysis(
        uploaded_at=uploaded_at,
        total_acne_count=total_acne_count,
        max_acne_part=max_acne_part,
        cause_organ=cause_organ
    )
    session_db.add(new_entry)
    session_db.commit()
    session_db.close()
    print(f"✅ 분석 결과 저장 완료: {uploaded_at}, {max_acne_part} 부위 (원인: {cause_organ})")

# ✅ 4️⃣ AI 분석 후 결과 페이지 이동
@app.route("/analyze", methods=["POST"])
def analyze():
    if 'file' not in request.files:
        return "파일이 없습니다!", 400

    file = request.files['file']
    if file.filename == '':
        return "선택된 파일이 없습니다!", 400

    try:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)

        # ✅ AI 모델 실행
        with open(file_path, "rb") as img_file:
            img, results = analyze_acne_by_parts_result(img_file)

        total_acne_count = results["total_acne_count"]
        max_acne_part = results["max_acne_part"]
        acne_count_by_part = results["acne_count_by_part"]

        # ✅ 결과를 세션에 저장하여 다른 페이지에서도 사용 가능
        session["last_results"] = {
            "total_acne_count": total_acne_count,
            "max_acne_part": max_acne_part,
            "acne_count_by_part": acne_count_by_part,
            "image_path": file_path
        }

        # ✅ 분석 결과에 따라 HTML 페이지 선택
        RESULT_PAGES = {
            "이마": "forehead.html",
            "코": "nose.html",
            "왼쪽볼": "leftcheek.html",
            "오른쪽볼": "rightcheek.html",
            "턱": "jaw.html"
        }
        template_file = RESULT_PAGES.get(max_acne_part, "result.html")

        return render_template(template_file, results=session["last_results"])
    except Exception as e:
        return f"모델 실행 중 오류 발생: {e}", 500

# ✅ 5️⃣ 분석 결과 저장 API (AJAX 요청)
@app.route("/save_result", methods=["POST"])
def save_result():
    data = request.json
    total_acne_count = data.get("total_acne_count")
    max_acne_part = data.get("max_acne_part")

    if total_acne_count is None or max_acne_part is None:
        return jsonify({"error": "저장할 데이터가 부족합니다."}), 400

    add_acne_analysis(total_acne_count, max_acne_part)
    return jsonify({"message": "분석 결과가 성공적으로 저장되었습니다!"})

# ✅ 6️⃣ 오른쪽 볼 결과 페이지 (rightcheek.html)
@app.route("/rightcheek")
def rightcheek():
    results = session.get("last_results", {})
    return render_template("rightcheek.html", results=results)

# ✅ 7️⃣ 기록 보기 페이지
@app.route("/record")
def history():
    session_db = SessionLocal()
    records = session_db.query(AcneAnalysis).all()
    session_db.close()
    return render_template("record.html", records=records)

# ✅ 8️⃣ 상세 정보 페이지 추가 (Polygon2 클릭 시 이동)
@app.route("/detail")
def detail():
    results = session.get("last_results", {})
    return render_template("detail.html", results=results)

# ✅ 9️⃣ 뒤로 가기 버튼이 항상 홈으로 이동하도록 설정
@app.route("/back_to_home")
def back_to_home():
    return redirect(url_for("index"))

# Flask 서버 실행
if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
