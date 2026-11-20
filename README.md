# ⚡ Meta Flow Production Platform

แพลตฟอร์มสร้างและจัดการวิดีโออัตโนมัติแบบ 3 ส่วน (**User App**, **Web Editor**, **Admin & AI Feature Factory**) ขับเคลื่อนด้วย FastAPI และ SQLite

## โครงสร้างระบบ
- **1. User App:** สร้างวิดีโอจาก Prompt แบบ Background Job, เติมเครดิตแพ็กเกจ และดาวน์โหลดไฟล์ MP4
- **2. Web Editor:** พื้นที่เลือกไฟล์วิดีโอหลายไฟล์และเตรียมจัดเรียงรอยต่อ Overlap 0.5s
- **3. Admin & AI Feature Factory:** ดูภาพรวมผู้ใช้ รายได้ รายการธุรกรรม และสร้าง/Deploy ร่างฟีเจอร์ใหม่

## การรันในเครื่อง
```bash
pip install -r requirements.txt
python meta_flow_production.py
