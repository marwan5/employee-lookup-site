import os
import re
from datetime import date, datetime

import pandas as pd
from flask import Flask, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=["60 per hour"])

# Set this to the Google Sheets spreadsheet ID or provide SHEET_CSV_URL.
GOOGLE_SHEET_ID = os.environ.get(
    "GOOGLE_SHEET_ID", "1yo-EQ1oy4JhMgYDu_Nk9ifsu7I0OFVNe"
)
SHEET_GID = os.environ.get("SHEET_GID", "0")
SHEET_CSV_URL = os.environ.get(
    "SHEET_CSV_URL",
    f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export?format=csv&gid={SHEET_GID}",
)
NATIONAL_ID_COLUMN = "الرقم الوطني"
PUBLIC_FIELDS = [
    "الاسم الكامل",
    "القطاع",
    "الإدارة التابع لها",
    "نوع الوظيفة",
    "حالة الموظف",
    "الفروقات",
]


def normalize_id(value):
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    if "e" in s.lower():
        try:
            s = format(int(float(s)), "d")
        except (ValueError, OverflowError):
            return ""
    return re.sub(r"\D", "", s)


def load_data():
    try:
        # The spreadsheet must be accessible for viewing by the server via its CSV export.
        df = pd.read_csv(SHEET_CSV_URL, dtype=str, keep_default_na=False)
    except Exception:
        app.logger.exception("Could not read Google Sheet CSV export")
        return None, (
            "تعذر الوصول إلى جدول Google Sheets. تأكد من أن إعداد المشاركة يسمح "
            "بالعرض عبر الرابط، وأن اسم ورقة العمل ورؤوس الأعمدة صحيحة."
        )

    df.columns = [str(column).strip() for column in df.columns]
    if NATIONAL_ID_COLUMN not in df.columns:
        return None, (
            "لم يُعثر على عمود «الرقم الوطني» في الصف الأول من الجدول. "
            "تأكد من كتابة اسم العمود كما هو تماماً؛ لن يظهر الرقم الوطني ضمن النتائج."
        )
    df["_normalized_id"] = df[NATIONAL_ID_COLUMN].map(normalize_id)
    return df, None


def display_value(value):
    if pd.isna(value) or str(value).strip() == "":
        return "—"
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


@app.get("/")
@limiter.limit("10 per minute")
def index():
    national_id = request.args.get("national_id", "").strip()
    result = None
    message = None

    if national_id:
        if not re.fullmatch(r"\d{5,20}", national_id):
            message = "يرجى إدخال رقم وطني صحيح."
        else:
            df, error = load_data()
            if error:
                message = error
            else:
                matches = df[df["_normalized_id"] == normalize_id(national_id)]
                if matches.empty:
                    message = "لا توجد بيانات مطابقة لرقم البحث."
                else:
                    row = matches.iloc[0]
                    result = [
                        (field, display_value(row[field]))
                        for field in PUBLIC_FIELDS
                        if field in df.columns
                    ]
                    if not result:
                        message = "لم يتم إعداد حقول العرض العامة في النظام."

    return render_template(
        "index.html",
        national_id=national_id,
        result=result,
        message=message,
    )


@app.errorhandler(429)
def rate_limited(_error):
    return render_template(
        "index.html", national_id="", result=None,
        message="تم تجاوز عدد محاولات البحث المسموح بها. يرجى المحاولة لاحقاً."
    ), 429


if __name__ == "__main__":
    # Local testing only. Use a production server such as gunicorn for deployment.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
