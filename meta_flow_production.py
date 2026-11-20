import os
import sqlite3
import datetime
from typing import List
import requests
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image
from moviepy.editor import ImageClip, AudioFileClip
from gtts import gTTS

app = FastAPI(
    title="Meta Flow Production Platform",
    version="7.1.0",
    description="Backend API + SQLite + Frontend 3 ส่วน + Admin AI Feature Factory"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
DB_FILE = os.path.join(BASE_DIR, "meta_flow.db")

app.mount("/files", StaticFiles(directory=OUTPUT_DIR), name="files")


# =====================================================================
# 1. DATABASE INITIALIZATION (SQLite Persistent Storage)
# =====================================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            tier TEXT NOT NULL,
            credits INTEGER NOT NULL DEFAULT 0,
            role TEXT NOT NULL DEFAULT 'user'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            tx_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            package TEXT NOT NULL,
            price_paid REAL NOT NULL DEFAULT 0,
            credits_added INTEGER NOT NULL DEFAULT 0,
            timestamp TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_jobs (
            job_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            status TEXT NOT NULL,
            filename TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_features (
            feature_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            backend_code TEXT NOT NULL,
            frontend_code TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    cursor.execute("SELECT 1 FROM users WHERE user_id = 'usr_001'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, username, tier, credits, role) VALUES (?, ?, ?, ?, ?)",
            ("usr_001", "พ่อธันวา (Nheng)", "Creator", 150, "admin")
        )

    conn.commit()
    conn.close()


init_db()


# =====================================================================
# 2. #SUM VIDEO ENGINE (Background Media Pipeline)
# =====================================================================
class MetaVideoAutomation:
    @staticmethod
    def update_job_status(job_id: str, status: str):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE video_jobs SET status = ? WHERE job_id = ?", (status, job_id))
        conn.commit()
        conn.close()

    @staticmethod
    def generate_single_video(job_id: str, prompt: str, filename: str):
        safe_name = os.path.basename(filename)
        if not safe_name.endswith(".mp4"):
            safe_name += ".mp4"

        stem = os.path.splitext(safe_name)[0]
        img_path = os.path.join(OUTPUT_DIR, f"{stem}.jpg")
        audio_path = os.path.join(OUTPUT_DIR, f"{stem}.mp3")
        output_path = os.path.join(OUTPUT_DIR, safe_name)

        try:
            MetaVideoAutomation.update_job_status(job_id, "processing")

            # 1. ดึงภาพจาก AI
            encoded_prompt = requests.utils.quote(f"{prompt}, cinematic lighting, high detail, 8k")
            ai_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&nologo=true"
            res = requests.get(ai_url, timeout=25)
            if res.status_code == 200 and res.content:
                with open(img_path, "wb") as f:
                    f.write(res.content)
            else:
                img = Image.new("RGB", (1280, 720), (15, 23, 42))
                img.save(img_path)

            # 2. สร้างเสียงบรรยายไทย
            narration = f"วิดีโอสร้างจากคำสั่ง {prompt} โดย Meta Flow"
            tts = gTTS(text=narration, lang="th", slow=False)
            tts.save(audio_path)

            # 3. ประกอบร่างด้วย MoviePy
            audio = AudioFileClip(audio_path)
            duration = max(6.0, float(audio.duration or 6.0))
            clip = ImageClip(img_path).set_duration(duration)
            clip = clip.resize(lambda t: 1.0 + 0.03 * (t / duration)).set_audio(audio)

            clip.write_videofile(
                output_path,
                fps=24,
                codec="libx264",
                audio_codec="aac",
                logger=None
            )
            clip.close()
            audio.close()

            if os.path.exists(img_path):
                os.remove(img_path)
            if os.path.exists(audio_path):
                os.remove(audio_path)

            MetaVideoAutomation.update_job_status(job_id, "completed")
        except Exception as e:
            print(f"[ERROR] Video generation failed ({job_id}): {e}")
            MetaVideoAutomation.update_job_status(job_id, "failed")


# =====================================================================
# 3. REQUEST SCHEMAS & API ENDPOINTS
# =====================================================================
class TopUpReq(BaseModel):
    user_id: str = "usr_001"
    package: str


class VideoReq(BaseModel):
    user_id: str = "usr_001"
    prompt: str
    filename: str = ""


class AIFeatureReq(BaseModel):
    prompt: str


class DeployFeatureReq(BaseModel):
    feature_id: str


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "meta-flow-platform", "time": datetime.datetime.now().isoformat()}


@app.get("/api/user/{user_id}")
def get_user(user_id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, tier, credits, role FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "status": "success",
            "data": {
                "user_id": row[0],
                "username": row[1],
                "tier": row[2],
                "credits": row[3],
                "role": row[4]
            }
        }
    raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้")


@app.post("/api/billing/topup")
def topup(req: TopUpReq):
    plans = {
        "pack_s": (99.0, 50),
        "pack_m": (299.0, 200),
        "pack_l": (599.0, 500),
    }
    if req.package not in plans:
        raise HTTPException(status_code=400, detail="แพ็กเกจไม่ถูกต้อง")

    price, credits_added = plans[req.package]
    now_iso = datetime.datetime.now().isoformat()
    tx_id = f"TX-{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (req.user_id,))
    user_row = cursor.fetchone()
    if not user_row:
        conn.close()
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้")

    cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (credits_added, req.user_id))
    cursor.execute(
        "INSERT INTO transactions (tx_id, user_id, package, price_paid, credits_added, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (tx_id, req.user_id, req.package, price, credits_added, now_iso)
    )
    conn.commit()

    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (req.user_id,))
    new_bal = cursor.fetchone()[0]
    conn.close()

    return {"status": "success", "new_balance": new_bal, "tx_id": tx_id}


@app.post("/api/video/create")
def create_video_job(req: VideoReq, background_tasks: BackgroundTasks):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="กรุณาระบุ Prompt")

    cost = 5
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    now_iso = datetime.datetime.now().isoformat()
    filename = req.filename.strip() or f"meta_{now_str}.mp4"
    if not filename.endswith(".mp4"):
        filename += ".mp4"
    filename = os.path.basename(filename)

    job_id = f"JOB-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    tx_id = f"TX-{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (req.user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้")
    if row[0] < cost:
        conn.close()
        raise HTTPException(status_code=400, detail=f"เครดิตไม่พอ (ต้องใช้ {cost} เครดิต)")

    cursor.execute("UPDATE users SET credits = credits - ? WHERE user_id = ?", (cost, req.user_id))
    cursor.execute(
        "INSERT INTO transactions (tx_id, user_id, package, price_paid, credits_added, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (tx_id, req.user_id, "video_gen", 0.0, -cost, now_iso)
    )
    cursor.execute(
        "INSERT INTO video_jobs (job_id, user_id, prompt, status, filename, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, req.user_id, req.prompt.strip(), "queued", filename, now_iso)
    )
    conn.commit()
    conn.close()

    background_tasks.add_task(MetaVideoAutomation.generate_single_video, job_id, req.prompt.strip(), filename)
    return {
        "status": "success",
        "message": "ส่งคิวสร้างวิดีโอเข้าสู่ Meta Flow แล้วครับ",
        "job_id": job_id,
        "filename": filename
    }


@app.get("/api/video/jobs/{user_id}")
def list_video_jobs(user_id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT job_id, prompt, status, filename, timestamp FROM video_jobs WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    jobs = []
    for r in rows:
        file_exists = os.path.exists(os.path.join(OUTPUT_DIR, r[3]))
        jobs.append({
            "job_id": r[0],
            "prompt": r[1],
            "status": r[2],
            "filename": r[3],
            "timestamp": r[4],
            "url": f"/files/{r[3]}" if (r[2] == "completed" and file_exists) else None
        })
    return {"status": "success", "jobs": jobs}


@app.get("/api/video/download/{filename}")
def download_video(filename: str):
    safe_name = os.path.basename(filename)
    path = os.path.join(OUTPUT_DIR, safe_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์วิดีโอ")
    return FileResponse(path, media_type="video/mp4", filename=safe_name)


@app.post("/api/admin/ai-feature/generate")
def generate_ai_feature(req: AIFeatureReq):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="กรุณากรอกคำสั่ง Prompt")

    clean_prompt = req.prompt.strip()
    feature_id = f"FEAT-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    slug = feature_id.lower().replace("-", "_")
    title = clean_prompt[:36] + ("..." if len(clean_prompt) > 36 else "")
    now_iso = datetime.datetime.now().isoformat()

    backend_code = (
        f"# Auto-generated FastAPI route for: {clean_prompt}\n"
        f"@app.get('/api/modules/{slug}')\n"
        f"def {slug}_endpoint():\n"
        f"    return {{'status': 'success', 'feature_id': '{feature_id}', 'prompt': {clean_prompt!r}}}"
    )

    frontend_code = (
        f"<div class='p-4 rounded-2xl bg-slate-900 border border-amber-500/30'>\n"
        f"  <h4 class='font-bold text-amber-400'>✨ {clean_prompt}</h4>\n"
        f"  <p class='text-xs text-slate-400 mt-1'>Module ID: {feature_id}</p>\n"
        f"</div>"
    )

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO ai_features (feature_id, title, prompt, backend_code, frontend_code, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (feature_id, title, clean_prompt, backend_code, frontend_code, "Draft", now_iso)
    )
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "feature_id": feature_id,
        "title": title,
        "backend_code": backend_code,
        "frontend_code": frontend_code,
        "feature_status": "Draft"
    }


@app.post("/api/admin/ai-feature/deploy")
def deploy_ai_feature(req: DeployFeatureReq):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE ai_features SET status = 'Deployed' WHERE feature_id = ?", (req.feature_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="ไม่พบฟีเจอร์ที่ต้องการ Deploy")
    conn.commit()
    conn.close()
    return {"status": "success", "feature_id": req.feature_id, "feature_status": "Deployed"}


@app.get("/api/admin/ai-features")
def list_ai_features():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT feature_id, title, prompt, status, timestamp FROM ai_features ORDER BY timestamp DESC")
    features = [
        {"feature_id": r[0], "title": r[1], "prompt": r[2], "status": r[3], "timestamp": r[4]}
        for r in cursor.fetchall()
    ]
    conn.close()
    return {"status": "success", "features": features}


@app.get("/api/admin/stats")
def admin_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(price_paid), 0) FROM transactions WHERE price_paid > 0")
    total_revenue = float(cursor.fetchone()[0] or 0.0)

    cursor.execute("SELECT COUNT(*) FROM video_jobs")
    total_jobs = cursor.fetchone()[0]

    cursor.execute(
        "SELECT tx_id, user_id, package, price_paid, credits_added, timestamp FROM transactions ORDER BY timestamp DESC LIMIT 15"
    )
    txs: List[dict] = [
        {
            "tx_id": r[0],
            "user_id": r[1],
            "package": r[2],
            "price_paid": r[3],
            "credits_added": r[4],
            "timestamp": r[5],
        }
        for r in cursor.fetchall()
    ]

    conn.close()
    return {
        "total_users": total_users,
        "total_revenue": total_revenue,
        "total_jobs": total_jobs,
        "transactions": txs,
    }


# =====================================================================
# 4. FRONTEND INTERFACE (3 ส่วน + Admin AI Feature Factory UI)
# =====================================================================
@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    return """
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Meta Flow - Production Platform</title>
        <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
        <style>
            .glass-card {
                background: rgba(17, 24, 39, 0.75);
                backdrop-filter: blur(12px);
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        </style>
    </head>
    <body class="bg-[#0b0f19] text-slate-100 font-sans min-h-screen">
        <header class="bg-slate-900/90 border-b border-slate-800 px-6 py-4 flex justify-between items-center flex-wrap gap-4 sticky top-0 z-50">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-gradient-to-tr from-cyan-400 to-blue-600 flex items-center justify-center font-black text-slate-950 text-xl">M</div>
                <div>
                    <h1 class="text-lg font-bold text-white">Meta <span class="text-cyan-400">Flow</span></h1>
                    <p class="text-[11px] text-slate-400">3-Tier Production & AI Feature Factory</p>
                </div>
            </div>

            <div class="flex gap-2 flex-wrap">
                <button onclick="switchView('userApp')" id="navUser" class="bg-cyan-500 text-slate-950 px-4 py-2 rounded-xl font-bold text-xs sm:text-sm transition">📱 1. User App</button>
                <button onclick="switchView('webApp')" id="navWeb" class="bg-slate-800 text-slate-300 px-4 py-2 rounded-xl font-bold text-xs sm:text-sm transition">🌐 2. Web Editor</button>
                <button onclick="switchView('adminCtrl')" id="navAdmin" class="bg-slate-800 text-slate-300 px-4 py-2 rounded-xl font-bold text-xs sm:text-sm transition">⚙️ 3. Admin & AI Factory</button>
            </div>
        </header>

        <main class="max-w-6xl mx-auto p-6 space-y-6">
            <!-- PART 1: USER APP -->
            <div id="viewUserApp" class="space-y-6">
                <div class="glass-card p-6 rounded-3xl grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div class="md:col-span-2 space-y-4">
                        <span class="inline-block bg-cyan-500/10 text-cyan-400 text-xs font-bold px-3 py-1 rounded-full border border-cyan-500/20">#sum Video Engine</span>
                        <h2 class="text-xl font-bold text-white">สร้างวิดีโออัตโนมัติจาก Prompt</h2>
                        <input id="promptInput" type="text" placeholder="ระบุ Prompt เช่น ทุ่งดอกไม้ยามเช้าที่ลำปาง แสงอบอุ่น" class="w-full bg-slate-950 border border-slate-700 p-3.5 rounded-2xl text-white text-sm focus:outline-none focus:border-cyan-500" />
                        <button onclick="createVideo()" class="w-full bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold py-3.5 rounded-2xl transition">สร้างวิดีโอ (-5 เครดิต)</button>
                    </div>

                    <div class="bg-slate-950/70 p-6 rounded-2xl border border-slate-800 flex flex-col justify-center items-center text-center">
                        <p class="text-xs text-slate-400">บัญชีผู้ใช้ปัจจุบัน</p>
                        <h3 id="lblUsername" class="font-bold text-lg text-white mt-1">กำลังโหลด...</h3>
                        <p class="text-cyan-400 font-mono text-2xl mt-2 font-bold"><span id="lblCredits">0</span> 💎</p>
                        <p class="text-xs text-slate-500 mt-1">เครดิตคงเหลือ</p>
                    </div>
                </div>

                <div class="glass-card p-6 rounded-3xl">
                    <h2 class="text-lg font-bold text-cyan-300 mb-4">💎 เติมเครดิตแพ็กเกจ</h2>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 text-center">
                            <h3 class="font-bold text-white">Starter Pack</h3>
                            <p class="text-2xl font-bold text-cyan-400 my-2">99 ฿</p>
                            <button onclick="topup('pack_s')" class="w-full bg-slate-800 hover:bg-cyan-500 hover:text-slate-950 py-2.5 rounded-xl font-bold text-xs transition">เติม 50 เครดิต</button>
                        </div>
                        <div class="bg-slate-950 p-4 rounded-2xl border border-cyan-500 text-center">
                            <h3 class="font-bold text-white">Creator Pack</h3>
                            <p class="text-2xl font-bold text-cyan-400 my-2">299 ฿</p>
                            <button onclick="topup('pack_m')" class="w-full bg-cyan-500 hover:bg-cyan-400 text-slate-950 py-2.5 rounded-xl font-bold text-xs transition">เติม 200 เครดิต</button>
                        </div>
                        <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 text-center">
                            <h3 class="font-bold text-white">Enterprise</h3>
                            <p class="text-2xl font-bold text-cyan-400 my-2">599 ฿</p>
                            <button onclick="topup('pack_l')" class="w-full bg-slate-800 hover:bg-cyan-500 hover:text-slate-950 py-2.5 rounded-xl font-bold text-xs transition">เติม 500 เครดิต</button>
                        </div>
                    </div>
                </div>

                <div class="glass-card p-6 rounded-3xl space-y-3">
                    <div class="flex justify-between items-center">
                        <h2 class="text-lg font-bold text-white">🎞️ คิวและผลงานวิดีโอของฉัน</h2>
                        <button onclick="loadVideoJobs()" class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg">รีเฟรชสถานะ</button>
                    </div>
                    <div id="videoJobsList" class="space-y-2 text-xs text-slate-300">กำลังโหลดรายการ...</div>
                </div>
            </div>

            <!-- PART 2: WEB APP EDITOR -->
            <div id="viewWebApp" class="hidden space-y-6">
                <div class="glass-card p-6 rounded-3xl space-y-4">
                    <h2 class="text-lg font-bold text-cyan-300">🌐 #sum Video Editor - Overlap 0.5s</h2>
                    <p class="text-sm text-slate-400">เลือกไฟล์วิดีโอหลายไฟล์เพื่อดูรายชื่อและเตรียมจัดเรียงรอยต่อ Overlap 0.5s</p>
                    <input id="editorFiles" type="file" accept="video/*" multiple onchange="renderSelectedFiles()" class="block w-full text-sm text-slate-400 file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-cyan-500 file:text-slate-950 hover:file:bg-cyan-400" />
                    <div id="selectedFilesList" class="text-xs text-slate-400 space-y-1">ยังไม่ได้เลือกไฟล์วิดีโอ</div>
                    <div class="bg-black aspect-video rounded-2xl flex items-center justify-center border border-slate-800 text-slate-500 text-sm">
                        [พื้นที่แสดงพรีวิว Overlap Crossfade 0.5s]
                    </div>
                </div>
            </div>

            <!-- PART 3: ADMIN CONTROL & AI FEATURE FACTORY -->
            <div id="viewAdminCtrl" class="hidden space-y-6">
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div class="glass-card p-6 rounded-2xl">
                        <p class="text-xs text-slate-400">ผู้ใช้งานทั้งหมด</p>
                        <h3 id="adminUsers" class="text-3xl font-black text-white mt-1">-- คน</h3>
                    </div>
                    <div class="glass-card p-6 rounded-2xl">
                        <p class="text-xs text-slate-400">รายได้รวมสุทธิ (THB)</p>
                        <h3 id="adminRevenue" class="text-3xl font-black text-emerald-400 mt-1">-- ฿</h3>
                    </div>
                    <div class="glass-card p-6 rounded-2xl">
                        <p class="text-xs text-slate-400">งานสร้างวิดีโอทั้งหมด</p>
                        <h3 id="adminJobs" class="text-3xl font-black text-cyan-400 mt-1">-- งาน</h3>
                    </div>
                </div>

                <div class="glass-card p-6 rounded-3xl space-y-4 border border-amber-500/30">
                    <h2 class="text-xl font-bold text-amber-400">✨ Admin AI Feature Factory</h2>
                    <p class="text-sm text-slate-400">สั่งสร้างฟีเจอร์หรือโมดูลใหม่สำหรับระบบ</p>

                    <div class="space-y-3">
                        <textarea id="aiPrompt" rows="3" placeholder="เช่น: สร้างระบบโค้ดส่วนลดและคูปองเครดิตสำหรับสมาชิกใหม่" class="w-full bg-slate-950 border border-slate-700 p-4 rounded-2xl text-white text-sm focus:outline-none focus:border-amber-500"></textarea>
                        <button onclick="generateFeature()" class="w-full bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold py-3.5 rounded-2xl transition">🪄 สร้างร่างโค้ดฟีเจอร์</button>
                    </div>

                    <div id="aiResultBox" class="hidden space-y-3 mt-4 pt-4 border-t border-slate-800">
                        <div class="flex justify-between items-center gap-2 flex-wrap">
                            <h3 class="font-bold text-white text-sm">
                                ฟีเจอร์: <span id="resTitle" class="text-amber-400"></span>
                                (<span id="resStatus" class="text-cyan-400">Draft</span>)
                            </h3>
                            <button onclick="deployCurrentFeature()" id="btnDeployFeature" class="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold px-4 py-2 rounded-xl text-xs transition">🚀 Deploy ฟีเจอร์นี้</button>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <p class="text-xs text-slate-400 mb-1">Backend Route Draft</p>
                                <pre id="resBackend" class="bg-slate-950 p-3 rounded-xl text-xs text-green-400 font-mono h-32 overflow-auto border border-slate-800"></pre>
                            </div>
                            <div>
                                <p class="text-xs text-slate-400 mb-1">Frontend UI Draft</p>
                                <pre id="resFrontend" class="bg-slate-950 p-3 rounded-xl text-xs text-cyan-400 font-mono h-32 overflow-auto border border-slate-800"></pre>
                            </div>
                        </div>
                    </div>

                    <div class="pt-2">
                        <h3 class="font-bold text-white text-sm mb-2">📦 รายการฟีเจอร์ในระบบ</h3>
                        <div id="aiFeaturesList" class="space-y-2 text-xs text-slate-300">กำลังโหลด...</div>
                    </div>
                </div>

                <div class="glass-card p-6 rounded-3xl">
                    <h3 class="font-bold text-white mb-2 text-sm">ประวัติธุรกรรมล่าสุด</h3>
                    <div id="adminTxList" class="bg-slate-950 p-4 rounded-xl border border-slate-800 text-xs font-mono text-slate-400 overflow-x-auto">
                        กำลังโหลดข้อมูล...
                    </div>
                </div>
            </div>
        </main>

        <script>
            const CURRENT_USER = "usr_001";
            let currentFeatureId = null;

            async function loadUser() {
                const res = await fetch(`/api/user/${CURRENT_USER}`);
                const data = await res.json();
                if (data.status === "success") {
                    document.getElementById("lblUsername").textContent = `${data.data.username} (${data.data.tier})`;
                    document.getElementById("lblCredits").textContent = data.data.credits;
                }
            }

            async function topup(pkg) {
                const res = await fetch("/api/billing/topup", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ user_id: CURRENT_USER, package: pkg })
                });
                const data = await res.json();
                if (res.ok && data.status === "success") {
                    alert(`เติมเครดิตสำเร็จ! ยอดคงเหลือ: ${data.new_balance} เครดิต`);
                    loadUser();
                } else {
                    alert(data.detail || "เติมเครดิตไม่สำเร็จ");
                }
            }

            async function createVideo() {
                const promptInput = document.getElementById("promptInput");
                const prompt = promptInput.value.trim();
                if (!prompt) return alert("กรุณากรอก Prompt ก่อนครับ");

                const res = await fetch("/api/video/create", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ user_id: CURRENT_USER, prompt })
                });
                const data = await res.json();
                if (res.ok && data.status === "success") {
                    alert(`${data.message} (${data.job_id})`);
                    promptInput.value = "";
                    loadUser();
                    loadVideoJobs();
                } else {
                    alert(data.detail || "สร้างงานไม่สำเร็จ");
                }
            }

            async function loadVideoJobs() {
                const res = await fetch(`/api/video/jobs/${CURRENT_USER}`);
                const data = await res.json();
                const box = document.getElementById("videoJobsList");
                if (!data.jobs || data.jobs.length === 0) {
                    box.innerHTML = `<p class="text-slate-500">ยังไม่มีรายการสร้างวิดีโอ</p>`;
                    return;
                }
                box.innerHTML = data.jobs.map(j => {
                    const dl = j.url
                        ? `<a href="/api/video/download/${encodeURIComponent(j.filename)}" class="bg-cyan-500 text-slate-950 font-bold px-3 py-1 rounded-lg">ดาวน์โหลด MP4</a>`
                        : `<span class="text-slate-500">${j.status}</span>`;
                    return `<div class="bg-slate-950 p-3 rounded-xl border border-slate-800 flex justify-between items-center gap-3 flex-wrap">
                        <div>
                            <span class="font-mono text-cyan-400">${j.job_id}</span> · <span>${j.prompt}</span>
                            <div class="text-[11px] text-slate-500">สถานะ: ${j.status} | ไฟล์: ${j.filename}</div>
                        </div>
                        <div>${dl}</div>
                    </div>`;
                }).join("");
            }

            function renderSelectedFiles() {
                const files = document.getElementById("editorFiles").files;
                const box = document.getElementById("selectedFilesList");
                if (!files || files.length === 0) {
                    box.textContent = "ยังไม่ได้เลือกไฟล์วิดีโอ";
                    return;
                }
                box.innerHTML = Array.from(files).map((f, i) =>
                    `<div class="bg-slate-950 px-3 py-2 rounded-lg border border-slate-800">${i + 1}. ${f.name} (${(f.size / (1024 * 1024)).toFixed(2)} MB)</div>`
                ).join("");
            }

            async function generateFeature() {
                const prompt = document.getElementById("aiPrompt").value.trim();
                if (!prompt) return alert("กรุณากรอกคำสั่ง Prompt");

                const res = await fetch("/api/admin/ai-feature/generate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt })
                });
                const data = await res.json();
                if (res.ok && data.status === "success") {
                    currentFeatureId = data.feature_id;
                    document.getElementById("aiResultBox").classList.remove("hidden");
                    document.getElementById("resTitle").textContent = data.title;
                    document.getElementById("resStatus").textContent = data.feature_status;
                    document.getElementById("resBackend").textContent = data.backend_code;
                    document.getElementById("resFrontend").textContent = data.frontend_code;
                    loadAIFeatures();
                } else {
                    alert(data.detail || "สร้างร่างฟีเจอร์ไม่สำเร็จ");
                }
            }

            async function deployCurrentFeature() {
                if (!currentFeatureId) return;
                const res = await fetch("/api/admin/ai-feature/deploy", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ feature_id: currentFeatureId })
                });
                const data = await res.json();
                if (res.ok && data.status === "success") {
                    document.getElementById("resStatus").textContent = data.feature_status;
                    alert(`อัปเดตสถานะ ${data.feature_id} เป็น Deployed เรียบร้อยครับ`);
                    loadAIFeatures();
                }
            }

            async function loadAIFeatures() {
                const res = await fetch("/api/admin/ai-features");
                const data = await res.json();
                const box = document.getElementById("aiFeaturesList");
                if (!data.features || data.features.length === 0) {
                    box.innerHTML = `<p class="text-slate-500">ยังไม่มีฟีเจอร์ในระบบ</p>`;
                    return;
                }
                box.innerHTML = data.features.map(f => `
                    <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 flex justify-between items-center gap-2">
                        <div>
                            <span class="font-bold text-white">${f.title}</span>
                            <span class="text-[11px] text-slate-500 font-mono ml-2">${f.feature_id}</span>
                        </div>
                        <span class="px-2.5 py-1 rounded-lg text-[11px] font-bold ${f.status === 'Deployed' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'}">${f.status}</span>
                    </div>
                `).join("");
            }

            async function loadAdminStats() {
                const res = await fetch("/api/admin/stats");
                const data = await res.json();
                document.getElementById("adminUsers").textContent = `${data.total_users} คน`;
                document.getElementById("adminRevenue").textContent = `${Number(data.total_revenue).toLocaleString()} ฿`;
                document.getElementById("adminJobs").textContent = `${data.total_jobs} งาน`;
                document.getElementById("adminTxList").innerHTML = (data.transactions || []).map(t =>
                    `[${t.timestamp}] Tx: ${t.tx_id} | User: ${t.user_id} | Pkg: ${t.package} | Paid: ${t.price_paid}฿ | Credits: ${t.credits_added}`
                ).join("<br>") || "ยังไม่มีประวัติธุรกรรม";
                loadAIFeatures();
            }

            function switchView(view) {
                document.getElementById("viewUserApp").classList.add("hidden");
                document.getElementById("viewWebApp").classList.add("hidden");
                document.getElementById("viewAdminCtrl").classList.add("hidden");

                document.getElementById("navUser").className = "bg-slate-800 text-slate-300 px-4 py-2 rounded-xl font-bold text-xs sm:text-sm transition";
                document.getElementById("navWeb").className = "bg-slate-800 text-slate-300 px-4 py-2 rounded-xl font-bold text-xs sm:text-sm transition";
                document.getElementById("navAdmin").className = "bg-slate-800 text-slate-300 px-4 py-2 rounded-xl font-bold text-xs sm:text-sm transition";

                if (view === "userApp") {
                    document.getElementById("viewUserApp").classList.remove("hidden");
                    document.getElementById("navUser").className = "bg-cyan-500 text-slate-950 px-4 py-2 rounded-xl font-bold text-xs sm:text-sm transition";
                    loadUser();
                    loadVideoJobs();
                } else if (view === "webApp") {
                    document.getElementById("viewWebApp").classList.remove("hidden");
                    document.getElementById("navWeb").className = "bg-cyan-500 text-slate-950 px-4 py-2 rounded-xl font-bold text-xs sm:text-sm transition";
                } else if (view === "adminCtrl") {
                    document.getElementById("viewAdminCtrl").classList.remove("hidden");
                    document.getElementById("navAdmin").className = "bg-amber-500 text-slate-950 px-4 py-2 rounded-xl font-bold text-xs sm:text-sm transition";
                    loadAdminStats();
                }
            }

            loadUser();
            loadVideoJobs();
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("meta_flow_production:app", host="0.0.0.0", port=port)

