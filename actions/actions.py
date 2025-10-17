import google.generativeai as genai
import os
import time
import requests
import unicodedata
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction

import sqlite3
import hashlib

class ActionDefaultFallback(Action):
    def name(self) -> Text:
        return "action_default_fallback"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        

        user_message = tracker.latest_message.get('text', '')
        confidence = tracker.latest_message.get('intent', {}).get('confidence', 0)

        print(f"🔍 Fallback triggered - Confidence: {confidence:.3f}")
        print(f"🤖 User question: {user_message}")

        
        fallback_count = tracker.get_slot("fallback_count") or 0
        fallback_count += 1

        print(f"🔢 Fallback count: {fallback_count}")

        if fallback_count >= 3:  # 🔒 CHẶN SAU 3 LẦN FALLBACK
            print("🚫 Blocking infinite loop - sending contact info")
            contact_msg = (
                "Hiện tại hệ thống đang gặp sự cố kỹ thuật. "
                "Vui lòng liên hệ trực tiếp:\n"
                "📞 Hotline: 024.335.25832\n"
                "📧 Email: khoadientu@ptit.edu.vn"
            )
            dispatcher.utter_message(text=contact_msg)
            return [SlotSet("fallback_count", 0)]  # Reset counter

        
        dispatcher.utter_message(text="Để tôi hỗ trợ bạn tốt hơn với câu hỏi này...")

        return [
            SlotSet("fallback_count", fallback_count),
            FollowupAction("action_fallback_gemini")
        ]


class ActionFallbackGemini(Action):
    def name(self) -> Text:
        return "action_fallback_gemini"

    def __init__(self):
        self.api_key = "AIzaSyDPhLWyxOi8VsgjlQyc0y23LSlpMyLoO2w"
        self.api_available = True

        
        self.models_priority = [
            'gemini-2.5-flash',
            'gemini-2.0-flash',
            'gemini-2.5-pro',
        ]
        self.current_model_index = 0
        self.max_model_retries = 2  # 🔒 Giới hạn retry model

        try:
            genai.configure(api_key=self.api_key)
            print("✅ Gemini configured successfully")
        except Exception as e:
            print(f"❌ Gemini config error: {e}")
            self.api_available = False

    def _call_gemini(self, prompt: str) -> str:
        
        if not self.api_available:
            return None

        original_model_index = self.current_model_index
        retry_count = 0

        while retry_count < self.max_model_retries * len(self.models_priority):
            model_name = self.models_priority[self.current_model_index]

            try:
                print(f"🔄 Trying model: {model_name} (attempt {retry_count + 1})")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=220,
                        temperature=0.3,
                    ),
                    request_options={'timeout': 8}
                )

                if response and response.text:
                    response_text = response.text.strip()
                    if self._validate_response(response_text):
                        print(f"✅ Success with model: {model_name}")
                        return response_text
                    else:
                        print(f"❌ Invalid response from {model_name}")

            except Exception as e:
                print(f"❌ Model {model_name} failed: {e}")

            
            self.current_model_index = (self.current_model_index + 1) % len(self.models_priority)
            retry_count += 1

            
            if self.current_model_index == original_model_index and retry_count > 0:
                print("🚫 All models exhausted")
                break

        
        self.current_model_index = 0
        return None

    def _validate_response(self, response_text: str) -> bool:
        
        if not response_text:
            return False

        invalid_patterns = [
            "câu hỏi nằm ngoài phạm vi tư vấn",
            "không thể trả lời",
            "i cannot",
            "i'm sorry",
            "xin lỗi tôi không thể trả lời",
            "nằm ngoài phạm vi hiểu biết"
        ]

        response_lower = response_text.lower()
        for pattern in invalid_patterns:
            if pattern in response_lower:
                print(f"🚫 Response contains invalid pattern: {pattern}")
                return False

        words = response_text.split()
        is_valid = 5 <= len(words) <= 120
        print(f"📊 Word count: {len(words)} -> {'Valid' if is_valid else 'Invalid'}")

        return is_valid

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_message = tracker.latest_message.get('text', '')

        
        system_prompt = """
Bạn là CHATBOT TƯ VẤN TUYỂN SINH CHÍNH THỨC của **Khoa Điện Tử – Học viện Công nghệ Bưu chính Viễn thông (PTIT)**.

🎯 **Mục tiêu:**
- Giải đáp thắc mắc về tuyển sinh Khoa Điện tử PTIT một cách ngắn gọn, dễ hiểu, có định hướng cho thí sinh.
- Giữ giọng văn thân thiện, rõ ràng, ưu tiên liệt kê bullet để dễ đọc.
- Giải đáp chính xác các câu hỏi liên quan tới PTIT 

🏫 **Thông tin cố định (KHÔNG ĐƯỢC THAY ĐỔI):**
- Địa chỉ: 96A Trần Phú, Hà Đông, Hà Nội
- Điện thoại: 024.335.25832
- Email: khoadientu@ptit.edu.vn

🎓 **Các ngành đào tạo:**
1. Kỹ thuật Điều khiển và Tự động hóa
2. Công nghệ Vi mạch Bán dẫn
3. Công nghệ Kỹ thuật Điện, Điện tử

📌 **Thông tin tuyển sinh tham khảo 2024:**
- Điểm chuẩn: 24 – 26 điểm (tùy ngành)
- Tổ hợp: A00 (Toán – Lý – Hóa), A01 (Toán – Lý – Anh)
- Chỉ tiêu: ~200 sinh viên
- Học phí: 15 – 20 triệu / học kỳ
- Thời gian đào tạo: 4.5 năm

🗂 **Hồ sơ đăng ký cơ bản gồm:**
- Phiếu đăng ký xét tuyển
- Học bạ + Bằng tốt nghiệp THPT (bản sao)
- Giấy khai sinh, CMND/CCCD (bản sao)
- Ảnh 3x4 (4 tấm)

🚫 **Giới hạn bắt BUỘC:**
- Chỉ trả lời về TUYỂN SINH TRƯỜNG HỌC VIỆN CÔNG NGHỆ BƯU CHÍNH VIỄN THÔNG PTIT – KHÔNG tư vấn trường khác.
- Nếu câu hỏi ngoài phạm vi → trả lời: "Câu hỏi nằm ngoài phạm vi tư vấn. Vui lòng liên hệ trực tiếp Khoa Điện Tử PTIT để được hỗ trợ."
- Nếu dữ liệu CHƯA CÔNG BỐ → trả lời rõ: "Hiện chưa có dữ liệu chính thức, bạn có thể theo dõi website hoặc hotline của khoa để cập nhật."

💬 **Quy tắc trả lời:**
- Dưới 80 từ.
- Ngắn gọn, chia gạch đầu dòng nếu phù hợp.
- Có thể dùng icon như ✅ 📌 📞 để tăng thân thiện.
- Không nói kiểu AI/robot, mà như người tư vấn tuyển sinh nhiệt tình.
- Nếu câu hỏi không liên quan đến tuyển sinh, có thể trả lời ngắn gọn và hướng dẫn liên hệ bộ phận chuyên môn
Hãy trả lời câu hỏi sau theo đúng quy tắc trên:
"""

        full_prompt = f"{system_prompt}\n{user_message}"

        try:
            bot_response = self._call_gemini(full_prompt)

            if bot_response:
                print(f"✅ Gemini response successful")
                dispatcher.utter_message(text=bot_response)
                # 🔒 RESET FALLBACK COUNTER khi thành công
                return [
                    SlotSet("fallback_count", 0),
                    SlotSet("ten_nganh", None),
                    SlotSet("nam", None),
                    SlotSet("awaiting_year", False),
                    SlotSet("awaiting_major", False),
                    SlotSet("awaiting_year_phuong_thuc", False)
                ]
            else:
                print("❌ All Gemini models failed")
                self._send_fallback_response(dispatcher)

        except Exception as e:
            print(f"💥 Critical Gemini error: {e}")
            self._send_fallback_response(dispatcher)

        return []

    def _send_fallback_response(self, dispatcher: CollectingDispatcher):
       
        fallback_responses = [
            "Hiện tôi chưa thể trả lời câu hỏi này. Bạn vui lòng liên hệ trực tiếp Khoa Điện Tử PTIT để được hỗ trợ chi tiết nhé! 📞",
            "Câu hỏi này cần được tư vấn chi tiết hơn. Bạn có thể liên hệ hotline 024.335.25832 để được giải đáp cụ thể! ✅",
            "Để đảm bảo thông tin chính xác, mời bạn liên hệ trực tiếp Khoa Điện Tử PTIT qua số 024.335.25832 📞"
        ]

        import random
        response = random.choice(fallback_responses)
        dispatcher.utter_message(text=response)


class ActionResetFallbackCount(Action):
   

    def name(self) -> Text:
        return "action_reset_fallback_count"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        print("🔄 Resetting fallback counter")
        return [SlotSet("fallback_count", 0)]

# //key noi voi database
def get_db_connection():
    conn = sqlite3.connect("user_data.db")
    conn.row_factory = sqlite3.Row
    return conn
#bam mat khau
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

class ActionRegister(Action):
    def name(self) -> Text:
        return "action_register"
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        username = tracker.get_slot("username")
        password = tracker.get_slot("password")

        if not username or not password:
            dispatcher.utter_message(text="Cannot be empty")
            return []
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            dispatcher.utter_message(text=f"Username '{username}' is already registered.")
        else:
            passwordHash = hash_password(password)
            cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, passwordHash))
            conn.commit()
        conn.close()
        return [SlotSet("password", None)]


class ActionLogin(Action):
    def name(self) -> Text:
        return "action_login"
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        username = tracker.get_slot("username")
        password = tracker.get_slot("password")
        if not username or not password:
            dispatcher.utter_message(text="Cannot be empty")
            return []
        conn = get_db_connection()
        cursor = conn.cursor()
        passwordHash = hash_password(password)
        cursor.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", (username, passwordHash))
        user = cursor.fetchone()
        conn.close()

        if user:
            dispatcher.utter_message(text=f"Login successfully! Welcome {user['username']}")
            return [SlotSet("logged_in", True), SlotSet("password", None)]
        else:
            dispatcher.utter_message(text=f"Username or password is incorrect")
            return [SlotSet("logged-in", False), SlotSet("password", None)]

class ActionLogout(Action):
    def name(self) -> Text:
        return "action_logout"
    def run(
        self,
        dispatcher: "CollectingDispatcher",
        tracker: Tracker,
        domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Logout successfully!")
        return [SlotSet("logged_out", False), SlotSet("password", None)]



def remove_accents(text: Text) -> Text:
    """Remove Vietnamese accents from text using unicodedata"""
    if not text:
        return text

    text = unicodedata.normalize('NFD', text)
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn')


def chuan_hoa_ten_nganh(ten_nganh: Text) -> Text:
    """Chuẩn hóa tên ngành từ entity - Dùng chung cho tất cả actions"""
    if not ten_nganh:
        return None

    ten_khong_dau = remove_accents(ten_nganh.lower())

    mapping = {
        "ky thuat dieu khien va tu dong hoa": "Kỹ thuật Điều khiển và Tự động hóa",
        "dieu khien tu dong hoa": "Kỹ thuật Điều khiển và Tự động hóa",
        "tu dong hoa": "Kỹ thuật Điều khiển và Tự động hóa",
        "automation": "Kỹ thuật Điều khiển và Tự động hóa",
        "dk tdh": "Kỹ thuật Điều khiển và Tự động hóa",
        "control automation": "Kỹ thuật Điều khiển và Tự động hóa",

        "cong nghe ky thuat dien dien tu": "Công nghệ Kỹ thuật Điện, Điện tử",
        "dien dien tu": "Công nghệ Kỹ thuật Điện, Điện tử",
        "dien tu": "Công nghệ Kỹ thuật Điện, Điện tử",
        "electrical engineering": "Công nghệ Kỹ thuật Điện, Điện tử",
        "ee": "Công nghệ Kỹ thuật Điện, Điện tử",

        "cong nghe vi mach ban dan": "Công nghệ Vi mạch Bán dẫn",
        "vi mach": "Công nghệ Vi mạch Bán dẫn",
        "ban dan": "Công nghệ Vi mạch Bán dẫn",
        "semiconductor": "Công nghệ Vi mạch Bán dẫn",
        "ic design": "Công nghệ Vi mạch Bán dẫn",
        "chip design": "Công nghệ Vi mạch Bán dẫn",
        "vm bd": "Công nghệ Vi mạch Bán dẫn"
    }

    for key, value in mapping.items():
        if key in ten_khong_dau:
            return value


    official_names = {
        "Kỹ thuật Điều khiển và Tự động hóa": "Kỹ thuật Điều khiển và Tự động hóa",
        "Công nghệ Kỹ thuật Điện, Điện tử": "Công nghệ Kỹ thuật Điện, Điện tử",
        "Công nghệ Vi mạch Bán dẫn": "Công nghệ Vi mạch Bán dẫn"
    }

    for official_name in official_names.keys():
        if official_name.lower() in ten_nganh.lower():
            return official_name

    return None



class ActionHoiThongTinNganh(Action):


    def name(self) -> Text:
        return "action_hoi_thong_tin_nganh"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None


        thong_tin_nganh = {
            "Kỹ thuật Điều khiển và Tự động hóa": {
                "ma_nganh": "7520216",
                "mo_ta_ngan": "Đào tạo kỹ sư chuyên về hệ thống điều khiển tự động, robotics, IoT và AI trong công nghiệp 4.0.",
                "diem_chuan": "24.5 điểm (2024)",
                "chi_tieu": "150 sinh viên",
                "co_hoi_viec_lam": "Kỹ sư điều khiển, robotics, IoT, PLC/SCADA",
                "website": "https://dientu.ptit.edu.vn/nganh-dieu-khien-tu-dong-hoa"
            },
            "Công nghệ Kỹ thuật Điện, Điện tử": {
                "ma_nganh": "7510301",
                "mo_ta_ngan": "Chuyên về điện công nghiệp, điện tử công suất, năng lượng tái tạo và hệ thống viễn thông.",
                "diem_chuan": "24.0 điểm (2024)",
                "chi_tieu": "170 sinh viên",
                "co_hoi_viec_lam": "Kỹ sư điện, điện tử, năng lượng, viễn thông",
                "website": "https://dientu.ptit.edu.vn/nganh-dien-dien-tu"
            },
            "Công nghệ Vi mạch Bán dẫn": {
                "ma_nganh": "7510302",
                "mo_ta_ngan": "Đào tạo kỹ sư thiết kế chip, vi mạch và hệ thống nhúng - lĩnh vực then chốt 4.0.",
                "diem_chuan": "25.0 điểm (2024)",
                "chi_tieu": "110 sinh viên",
                "co_hoi_viec_lam": "Kỹ sư thiết kế chip, embedded systems, hardware",
                "website": "https://dientu.ptit.edu.vn/nganh-vi-mach-ban-dan"
            }
        }

        if ten_nganh_chuan and ten_nganh_chuan in thong_tin_nganh:
            info = thong_tin_nganh[ten_nganh_chuan]
            message = f"🎯 **{ten_nganh_chuan}**\n\n"
            message += f"📖 {info['mo_ta_ngan']}\n\n"
            message += f"🔢 **Mã ngành:** {info['ma_nganh']}\n"
            message += f"⭐ **Điểm chuẩn:** {info['diem_chuan']}\n"
            message += f"🎯 **Chỉ tiêu:** {info['chi_tieu']}\n"
            message += f"💼 **Cơ hội việc làm:** {info['co_hoi_viec_lam']}\n\n"
            message += f"🌐 **Xem chi tiết:** {info['website']}\n\n"
            message += "💡 *Liên hệ: (024) 3354 5678 | dientu@ptit.edu.vn*"

        elif ten_nganh:
            message = f"🔍 Tôi thấy bạn quan tâm '{ten_nganh}'. Khoa Điện tử - PTIT có 3 ngành:\n\n"
            message += self._tao_danh_sach_nganh(thong_tin_nganh)

        else:
            message = "🤖 **CÁC NGÀNH ĐÀO TẠO - KHOA ĐIỆN TỬ PTIT**\n\n"
            message += self._tao_danh_sach_nganh(thong_tin_nganh)

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh)]

    def _tao_danh_sach_nganh(self, thong_tin_nganh: Dict) -> Text:
        """Tạo danh sách các ngành"""
        message = ""
        for ten_nganh, info in thong_tin_nganh.items():
            message += f"• **{ten_nganh}**\n"
            message += f"  {info['mo_ta_ngan']}\n"
            message += f"  🔢 {info['ma_nganh']} | ⭐ {info['diem_chuan']}\n\n"

        message += "💬 *Hỏi chi tiết về ngành cụ thể để biết thêm thông tin!*"
        return message


class ActionTraCuuMaNganh(Action):


    def name(self) -> Text:
        return "action_tra_cuu_ma_nganh"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None

        ma_nganh_data = {
            "Kỹ thuật Điều khiển và Tự động hóa": "7520216",
            "Công nghệ Kỹ thuật Điện, Điện tử": "7510301",
            "Công nghệ Vi mạch Bán dẫn": "7510302"
        }

        if ten_nganh_chuan and ten_nganh_chuan in ma_nganh_data:
            ma_nganh = ma_nganh_data[ten_nganh_chuan]
            message = f"🔢 **Mã ngành {ten_nganh_chuan}:** {ma_nganh}\n\n"
            message += f"🏫 Mã trường: BKA (PTIT)\n"
            message += "💡 Sử dụng mã này khi đăng ký xét tuyển\n"
            message += "🌐 Chi tiết: https://tuyensinh.ptit.edu.vn"

        elif ten_nganh:
            message = f"❌ Không tìm thấy mã ngành cho '{ten_nganh}'\n\n"
            message += self._tao_danh_sach_ma_nganh(ma_nganh_data)

        else:
            message = "📋 **DANH SÁCH MÃ NGÀNH KHOA ĐIỆN TỬ**\n\n"
            message += self._tao_danh_sach_ma_nganh(ma_nganh_data)

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh)]

    def _tao_danh_sach_ma_nganh(self, ma_nganh_data: Dict) -> Text:
        """Tạo danh sách mã ngành"""
        message = ""
        for ten_nganh, ma_nganh in ma_nganh_data.items():
            message += f"• **{ten_nganh}:** {ma_nganh}\n"

        message += "\n💬 *Hỏi mã ngành cụ thể để biết thêm thông tin!*"
        return message


class ActionTraCuuDiemChuan(Action):


    def name(self) -> Text:
        return "action_tra_cuu_diem_chuan"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        nam = tracker.get_slot("nam")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None

        if not nam:
            nam = "2024"

        diem_chuan_data = {
            "2024": {
                "Kỹ thuật Điều khiển và Tự động hóa": "24.5 điểm",
                "Công nghệ Kỹ thuật Điện, Điện tử": "24.0 điểm",
                "Công nghệ Vi mạch Bán dẫn": "25.0 điểm"
            },
            "2023": {
                "Kỹ thuật Điều khiển và Tự động hóa": "24.0 điểm",
                "Công nghệ Kỹ thuật Điện, Điện tử": "23.5 điểm",
                "Công nghệ Vi mạch Bán dẫn": "24.5 điểm"
            },
            "2025": {
                "Kỹ thuật Điều khiển và Tự động hóa": "25.0 điểm",
                "Công nghệ Kỹ thuật Điện, Điện tử": "24.5 điểm",
                "Công nghệ Vi mạch Bán dẫn": "25.5 điểm"
            }
        }

        if nam not in diem_chuan_data:
            message = f"❌ Chưa có dữ liệu điểm chuẩn năm {nam}\n"
            message += f"📊 Các năm có dữ liệu: {', '.join(diem_chuan_data.keys())}"
            dispatcher.utter_message(text=message)
            return []

        nam_data = diem_chuan_data[nam]

        if ten_nganh_chuan and ten_nganh_chuan in nam_data:
            diem = nam_data[ten_nganh_chuan]
            message = f"📊 **Điểm chuẩn {nam} - {ten_nganh_chuan}**\n\n"
            message += f"⭐ {diem}\n\n"
            message += "🌐 Xem chi tiết: https://tuyensinh.ptit.edu.vn/diem-chuan"

        elif ten_nganh:
            message = f"❌ Không tìm thấy điểm chuẩn cho '{ten_nganh}' năm {nam}\n\n"
            message += self._tao_danh_sach_diem_chuan(nam_data, nam)

        else:
            message = f"📊 **ĐIỂM CHUẨN CÁC NGÀNH NĂM {nam}**\n\n"
            message += self._tao_danh_sach_diem_chuan(nam_data, nam)

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh), SlotSet("nam", nam)]

    def _tao_danh_sach_diem_chuan(self, nam_data: Dict, nam: Text) -> Text:
        """Tạo danh sách điểm chuẩn"""
        message = ""
        for ten_nganh, diem in nam_data.items():
            message += f"• **{ten_nganh}:** {diem}\n"

        message += f"\n🌐 Chi tiết: https://tuyensinh.ptit.edu.vn/diem-chuan-{nam}"
        message += f"\n💡 Điểm theo thang 30, xét tổ hợp A00, A01, D01, D07"
        return message


class ActionTraCuuKhaNangTrungTuyen(Action):


    def name(self) -> Text:
        return "action_tra_cuu_kha_nang_trung_tuyen"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        diem = tracker.get_slot("diem")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None

        if not diem:
            message = "🔍 **ĐỂ TƯ VẤN KHẢ NĂNG TRÚNG TUYỂN**\n\n"
            message += "Vui lòng cung cấp điểm số của bạn.\n"
            message += "💡 *Ví dụ: \"Em được 25 điểm có đỗ ngành Điều khiển Tự động hóa không?\"*"
            dispatcher.utter_message(text=message)
            return []

        try:
            diem_float = float(diem)
        except ValueError:
            message = "❌ Điểm số không hợp lệ. Vui lòng nhập điểm dạng số.\n"
            message += "💡 *Ví dụ: 24.5, 25, 26.75*"
            dispatcher.utter_message(text=message)
            return []


        diem_chuan_tham_khao = {
            "Kỹ thuật Điều khiển và Tự động hóa": 24.5,
            "Công nghệ Kỹ thuật Điện, Điện tử": 24.0,
            "Công nghệ Vi mạch Bán dẫn": 25.0
        }

        if ten_nganh_chuan and ten_nganh_chuan in diem_chuan_tham_khao:
            diem_chuan = diem_chuan_tham_khao[ten_nganh_chuan]
            chech_lech = diem_float - diem_chuan

            message = f"📊 **ĐÁNH GIÁ KHẢ NĂNG TRÚNG TUYỂN**\n\n"
            message += f"🎯 **Ngành:** {ten_nganh_chuan}\n"
            message += f"⭐ **Điểm của bạn:** {diem_float}\n"
            message += f"📈 **Điểm chuẩn 2024:** {diem_chuan}\n\n"

            if chech_lech >= 1.0:
                message += "✅ **KHẢ NĂNG CAO** - Cơ hội trúng tuyển rất tốt\n"
                message += "💡 Nên đặt nguyện vọng 1-2\n"
            elif chech_lech >= 0.5:
                message += "🟡 **KHẢ NĂNG TRUNG BÌNH** - Có cơ hội trúng tuyển\n"
                message += "💡 Nên đặt nguyện vọng 2-3\n"
            elif chech_lech >= 0:
                message += "🟠 **KHẢ NĂNG THẤP** - Cần cân nhắc\n"
                message += "💡 Nên đặt nguyện vọng 3-4 và có nguyện vọng dự phòng\n"
            else:
                message += "🔴 **CẦN CÂN NHẮC** - Điểm dưới chuẩn\n"
                message += "💡 Nên xem xét ngành khác hoặc ôn tập thêm\n"

            message += f"\n📉 **Chênh lệch:** {chech_lech:+.1f} điểm\n\n"
            message += "🌐 **Tham khảo:** https://tuyensinh.ptit.edu.vn/diem-chuan"

        elif ten_nganh:
            message = f"🔍 **ĐÁNH GIÁ KHẢ NĂNG TRÚNG TUYỂN**\n\n"
            message += f"⭐ **Điểm của bạn:** {diem_float}\n\n"
            message += "📊 **So sánh với điểm chuẩn 2024:**\n"

            for nganh, diem_chuan in diem_chuan_tham_khao.items():
                chech_lech = diem_float - diem_chuan
                if chech_lech >= 1.0:
                    danh_gia = "✅ CAO"
                elif chech_lech >= 0.5:
                    danh_gia = "🟡 TRUNG BÌNH"
                elif chech_lech >= 0:
                    danh_gia = "🟠 THẤP"
                else:
                    danh_gia = "🔴 DƯỚI CHUẨN"

                message += f"• **{nganh}:** {diem_chuan} điểm ({danh_gia})\n"

            message += f"\n💡 **Lời khuyên:**\n"
            if diem_float >= 25.0:
                message += "• Có thể đăng ký tất cả ngành\n• Ưu tiên ngành có điểm cao\n"
            elif diem_float >= 24.0:
                message += "• Phù hợp với Điều khiển TĐH & Điện Điện tử\n• Cân nhắc nguyện vọng Vi mạch\n"
            else:
                message += "• Nên ôn tập thêm để cải thiện điểm\n• Xem xét các nguyện vọng an toàn\n"

            message += "\n🌐 **Chi tiết:** https://tuyensinh.ptit.edu.vn"

        else:
            message = f"🔍 **ĐÁNH GIÁ KHẢ NĂNG TRÚNG TUYỂN**\n\n"
            message += f"⭐ **Điểm của bạn:** {diem_float}\n\n"
            message += "📊 **Điểm chuẩn tham khảo 2024:**\n"
            message += "• Điều khiển Tự động hóa: 24.5 điểm\n"
            message += "• Điện - Điện tử: 24.0 điểm\n"
            message += "• Vi mạch Bán dẫn: 25.0 điểm\n\n"
            message += "💡 **Hỏi cụ thể:** \"{diem_float} điểm có đỗ ngành [tên ngành] không?\""

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh), SlotSet("diem", diem)]


class ActionXetTuyenDieuKienDienTu(Action):


    def name(self) -> Text:
        return "action_xet_tuyen_dieu_kien_dien_tu"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None

        dieu_kien_chung = {
            "title": "📝 **ĐIỀU KIỆN XÉT TUYỂN CHUNG**",
            "conditions": [
                "✅ Tốt nghiệp THPT hoặc tương đương",
                "✅ Điểm xét tuyển theo tổ hợp môn",
                "✅ Học lực lớp 12 từ Trung bình trở lên",
                "✅ Đáp ứng điều kiện sức khỏe theo quy định",
                "✅ Không trong thời gian thi hành kỷ luật"
            ]
        }

        dieu_kien_nganh = {
            "Kỹ thuật Điều khiển và Tự động hóa": {
                "to_hop": "A00, A01, D01, D07",
                "mon_yeu_cau": "Toán, Lý, Hóa/Anh",
                "diem_toi_thieu": "Điểm mỗi môn >= 5.0",
                "ghi_chu": "Ưu tiên thí sinh có tư duy logic"
            },
            "Công nghệ Kỹ thuật Điện, Điện tử": {
                "to_hop": "A00, A01, D01, D07",
                "mon_yeu_cau": "Toán, Lý, Hóa/Anh",
                "diem_toi_thieu": "Điểm mỗi môn >= 5.0",
                "ghi_chu": "Phù hợp thí sinh yêu thích kỹ thuật"
            },
            "Công nghệ Vi mạch Bán dẫn": {
                "to_hop": "A00, A01, D01, D07",
                "mon_yeu_cau": "Toán, Lý, Hóa/Anh",
                "diem_toi_thieu": "Điểm mỗi môn >= 6.0",
                "ghi_chu": "Yêu cầu tư duy logic và sáng tạo cao"
            }
        }

        if ten_nganh_chuan and ten_nganh_chuan in dieu_kien_nganh:
            info = dieu_kien_nganh[ten_nganh_chuan]
            message = f"📋 **ĐIỀU KIỆN XÉT TUYỂN - {ten_nganh_chuan.upper()}**\n\n"

            message += f"{dieu_kien_chung['title']}\n"
            for condition in dieu_kien_chung['conditions']:
                message += f"{condition}\n"

            message += f"\n🎯 **ĐIỀU KIỆN RIÊNG:**\n"
            message += f"• **Tổ hợp xét tuyển:** {info['to_hop']}\n"
            message += f"• **Môn học yêu cầu:** {info['mon_yeu_cau']}\n"
            message += f"• **Điểm tối thiểu:** {info['diem_toi_thieu']}\n"
            message += f"• **Ghi chú:** {info['ghi_chu']}\n\n"

            message += "💡 **Lưu ý:**\n"
            message += "• Điểm xét tuyển = Tổng điểm 3 môn theo tổ hợp\n"
            message += "• Ưu tiên theo khu vực, đối tượng\n"
            message += "• Có thể thay đổi theo quy định từng năm\n\n"

            message += "🌐 **Chi tiết:** https://tuyensinh.ptit.edu.vn/dieu-kien"

        elif ten_nganh:
            message = f"🔍 Điều kiện xét tuyển cho '{ten_nganh}'\n\n"
            message += f"{dieu_kien_chung['title']}\n"
            for condition in dieu_kien_chung['conditions']:
                message += f"{condition}\n"

            message += f"\n📚 **Các ngành khoa Điện tử:**\n"
            for nganh in dieu_kien_nganh.keys():
                message += f"• {nganh}\n"

            message += f"\n💡 Hỏi cụ thể về ngành để biết điều kiện riêng"

        else:
            message = f"{dieu_kien_chung['title']}\n\n"
            for condition in dieu_kien_chung['conditions']:
                message += f"{condition}\n"

            message += f"\n🎯 **CÁC NGÀNH KHOA ĐIỆN TỬ:**\n"
            for nganh, info in dieu_kien_nganh.items():
                message += f"• **{nganh}** - {info['to_hop']}\n"

            message += f"\n💡 **Hỏi cụ thể:** \"Điều kiện xét tuyển ngành [tên ngành]\"\n"
            message += "🌐 **Xem chi tiết:** https://tuyensinh.ptit.edu.vn/dieu-kien"

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh)]


class ActionXetTuyenUuTienDienTu(Action):


    def name(self) -> Text:
        return "action_xet_tuyen_uu_tien_dien_tu"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None

        uu_tien_data = {
            "khu_vuc": {
                "KV1": "0.75 điểm - Vùng cao, hải đảo, biên giới",
                "KV2": "0.5 điểm - Các thị xã, thành phố trực thuộc tỉnh",
                "KV2-NT": "0.5 điểm - Vùng nông thôn KV2",
                "KV3": "0.25 điểm - Các quận nội thành"
            },
            "doi_tuong": {
                "01": "2.0 điểm - Công nhân trực tiếp",
                "02": "2.0 điểm - Bộ đội, công an tại ngũ",
                "03": "2.0 điểm - Lao động tiên tiến",
                "04": "1.5 điểm - Con liệt sĩ",
                "05": "1.5 điểm - Con thương binh",
                "06": "1.0 điểm - Người dân tộc thiểu số",
                "07": "1.0 điểm - Người khuyết tật"
            },
            "tuyen_thang": {
                "Học sinh giỏi Quốc gia": "Tuyển thẳng vào tất cả ngành",
                "Học sinh trường chuyên": "Ưu tiên xét tuyển",
                "Thí sinh Olympic": "Xét tuyển thẳng theo quy định",
                "Thí sinh tài năng": "Xét theo hồ sơ năng lực"
            }
        }


        message = "🎯 **CHÍNH SÁCH ƯU TIÊN XÉT TUYỂN**\n\n"

        message += "📍 **ƯU TIÊN KHU VỰC:**\n"
        for kv, mota in uu_tien_data["khu_vuc"].items():
            message += f"• **{kv}:** {mota}\n"

        message += f"\n👥 **ƯU TIÊN ĐỐI TƯỢNG:**\n"
        for dt, mota in uu_tien_data["doi_tuong"].items():
            message += f"• **ĐT{dt}:** {mota}\n"

        message += f"\n🏆 **TUYỂN THẲNG & ƯU TIÊN:**\n"
        for tt, mota in uu_tien_data["tuyen_thang"].items():
            message += f"• **{tt}:** {mota}\n"

        if ten_nganh_chuan:
            message += f"\n🎯 **ÁP DỤNG CHO NGÀNH {ten_nganh_chuan.upper()}:**\n"
            message += "✅ Áp dụng tất cả chính sách ưu tiên trên\n"
            message += "✅ Điểm ưu tiên được cộng vào tổng điểm xét tuyển\n"
            message += "✅ Có thể kết hợp nhiều diện ưu tiên\n"

        message += f"\n💡 **Lưu ý quan trọng:**\n"
        message += "• Điểm ưu tiên = Điểm khu vực + Điểm đối tượng\n"
        message += "• Tổng điểm ưu tiên tối đa: 2.25 điểm\n"
        message += "• Chỉ áp dụng 01 diện ưu tiên cao nhất\n"
        message += "• Cần có giấy tờ chứng minh hợp lệ\n\n"

        message += "📞 **Hỗ trợ:** Phòng Đào tạo - (024) 3354 5689\n"
        message += "🌐 **Chi tiết:** https://tuyensinh.ptit.edu.vn/uu-tien"

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh)]


class ActionXetTuyenHoSo(Action):
    """Action for providing admission application documentation information"""

    def name(self) -> Text:
        return "action_xet_tuyen_ho_so"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None


        ho_so_xet_tuyen = {
            "thanh_phan_ho_so": [
                "✅ **Phiếu đăng ký xét tuyển** (theo mẫu của trường)",
                "✅ **Bản sao học bạ THPT** (có công chứng)",
                "✅ **Bản sao bằng tốt nghiệp THPT** hoặc **Giấy chứng nhận tốt nghiệp tạm thời**",
                "✅ **Bản sao CMND/CCCD** (có công chứng)",
                "✅ **Giấy chứng nhận ưu tiên** (nếu có)",
                "✅ **Ảnh 3x4** (4 tấm, ghi rõ họ tên, ngày sinh phía sau)",
                "✅ **Phong bì có dán tem** (ghi rõ địa chỉ nhận giấy báo)"
            ],
            "yeu_cau_cong_chung": [
                "Tất cả bản sao phải được công chứng trong vòng 6 tháng",
                "Học bạ công chứng toàn bộ các trang",
                "Bằng tốt nghiệp/Giấy CN tốt nghiệp công chứng",
                "CMND/CCCD công chứng mặt trước và sau"
            ],
            "hinh_thuc_nop_ho_so": {
                "truc_tiep": "Nộp trực tiếp tại Phòng Đào tạo - PTIT",
                "buu_dien": "Gửi hồ sơ qua bưu điện theo địa chỉ tuyển sinh",
                "online": "Đăng ký online qua cổng tuyển sinh của Bộ GD&ĐT và PTIT"
            },
            "dia_chi_nop_ho_so": {
                "co_so_ha_noi": "Phòng Đào tạo, Tầng 1, Nhà A1, 122 Hoàng Quốc Việt, Cầu Giấy, Hà Nội",
                "co_so_hcm": "Phòng Đào tạo, 11 Nguyễn Đình Chiểu, P. Đa Kao, Quận 1, TP.HCM",
                "thoi_gian_lam_viec": "Thứ 2 - Thứ 6: 7h30 - 17h00, Thứ 7: 7h30 - 12h00"
            },
            "le_phi": {
                "phi_xet_tuyen": "30.000 VNĐ/nguyện vọng",
                "phi_nhap_hoc": "Theo thông báo khi trúng tuyển",
                "hinh_thuc_dong": "Chuyển khoản hoặc nộp trực tiếp"
            },
            "thoi_gian": {
                "mo_dang_ky": "01/04 hàng năm",
                "ket_thuc_dot_1": "20/06 hàng năm",
                "dot_bo_sung": "Theo thông báo của trường",
                "cong_khai_ket_qua": "15-20 ngày sau khi nộp hồ sơ"
            },
            "huong_dan_online": {
                "buoc_1": "Truy cập https://dangky.ptit.edu.vn",
                "buoc_2": "Đăng ký tài khoản và điền thông tin cá nhân",
                "buoc_3": "Chọn ngành, tổ hợp xét tuyển",
                "buoc_4": "Tải lên bản scan các giấy tờ cần thiết",
                "buoc_5": "Xác nhận và nộp lệ phí online",
                "buoc_6": "Theo dõi kết quả và xác nhận nhập học"
            }
        }

        message = "📋 **HƯỚNG DẪN HỒ SƠ XÉT TUYỂN - KHOA ĐIỆN TỬ PTIT**\n\n"


        message += "🎒 **THÀNH PHẦN HỒ SƠ ĐẦY ĐỦ:**\n"
        for thanh_phan in ho_so_xet_tuyen['thanh_phan_ho_so']:
            message += f"{thanh_phan}\n"

        message += "\n🏛️ **YÊU CẦU CÔNG CHỨNG:**\n"
        for yeu_cau in ho_so_xet_tuyen['yeu_cau_cong_chung']:
            message += f"• {yeu_cau}\n"


        message += "\n📮 **HÌNH THỨC NỘP HỒ SƠ:**\n"
        message += f"• **Trực tiếp:** {ho_so_xet_tuyen['hinh_thuc_nop_ho_so']['truc_tiep']}\n"
        message += f"• **Bưu điện:** {ho_so_xet_tuyen['hinh_thuc_nop_ho_so']['buu_dien']}\n"
        message += f"• **Online:** {ho_so_xet_tuyen['hinh_thuc_nop_ho_so']['online']}\n"


        message += "\n📍 **ĐỊA CHỈ NỘP HỒ SƠ:**\n"
        message += f"• **Hà Nội:** {ho_so_xet_tuyen['dia_chi_nop_ho_so']['co_so_ha_noi']}\n"
        message += f"• **TP.HCM:** {ho_so_xet_tuyen['dia_chi_nop_ho_so']['co_so_hcm']}\n"
        message += f"• **Thời gian làm việc:** {ho_so_xet_tuyen['dia_chi_nop_ho_so']['thoi_gian_lam_viec']}\n"


        message += "\n💰 **LỆ PHÍ XÉT TUYỂN:**\n"
        message += f"• **Phí xét tuyển:** {ho_so_xet_tuyen['le_phi']['phi_xet_tuyen']}\n"
        message += f"• **Phí nhập học:** {ho_so_xet_tuyen['le_phi']['phi_nhap_hoc']}\n"
        message += f"• **Hình thức đóng:** {ho_so_xet_tuyen['le_phi']['hinh_thuc_dong']}\n"


        message += "\n⏰ **THỜI GIAN TUYỂN SINH:**\n"
        message += f"• **Mở đăng ký:** {ho_so_xet_tuyen['thoi_gian']['mo_dang_ky']}\n"
        message += f"• **Kết thúc đợt 1:** {ho_so_xet_tuyen['thoi_gian']['ket_thuc_dot_1']}\n"
        message += f"• **Đợt bổ sung:** {ho_so_xet_tuyen['thoi_gian']['dot_bo_sung']}\n"
        message += f"• **Công bố kết quả:** {ho_so_xet_tuyen['thoi_gian']['cong_khai_ket_qua']}\n"


        message += "\n💻 **HƯỚNG DẪN ĐĂNG KÝ ONLINE:**\n"
        for buoc, huong_dan in ho_so_xet_tuyen['huong_dan_online'].items():
            message += f"• **{buoc.replace('_', ' ').title()}:** {huong_dan}\n"


        message += "\n❓ **CÂU HỎI THƯỜNG GẶP:**\n"
        message += "• **Nộp online có cần nộp bản cứng?** Chỉ cần nộp bản cứng khi nhập học\n"
        message += "• **Sai thông tin có sửa được?** Được sửa trong thời hạn đăng ký\n"
        message += "• **Thiếu giấy tờ?** Bổ sung trong vòng 7 ngày sau khi nộp\n"
        message += "• **Nộp muộn?** Chỉ được nộp trong các đợt bổ sung (nếu có)\n"


        if ten_nganh_chuan:
            message += f"\n🎯 **LƯU Ý CHO NGÀNH {ten_nganh_chuan.upper()}:**\n"
            message += "• Hồ sơ giống các ngành khác trong khoa Điện tử\n"
            message += "• Không yêu cầu giấy tờ đặc biệt nào khác\n"
            message += "• Ưu tiên xét hồ sơ nộp sớm\n"


        message += "\n📞 **HỖ TRỢ HỒ SƠ:**\n"
        message += "• **Hotline:** (024) 3354 5678\n"
        message += "• **Email:** tuyensinh@ptit.edu.vn\n"
        message += "• **Website:** https://tuyensinh.ptit.edu.vn\n"
        message += "• **Fanpage:** https://facebook.com/ptit.tuyensinh\n"

        message += "\n💡 **LỜI KHUYÊN:**\n"
        message += "• Chuẩn bị hồ sơ sớm, tránh nước đến chân mới nhảy\n"
        message += "• Kiểm tra kỹ thông tin trước khi nộp\n"
        message += "• Giữ lại biên lai/bản sao hồ sơ đã nộp\n"
        message += "• Theo dõi thông báo thường xuyên trên website trường\n"

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh)]


class ActionTraCuuChiTieu(Action):
    """Action for looking up enrollment quotas by major"""

    def name(self) -> Text:
        return "action_tra_cuu_chi_tieu"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        nam = tracker.get_slot("nam")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None

        if not nam:
            nam = "2024"


        chi_tieu_data = {
            "2024": {
                "Kỹ thuật Điều khiển và Tự động hóa": "150 chỉ tiêu",
                "Công nghệ Kỹ thuật Điện, Điện tử": "170 chỉ tiêu",
                "Công nghệ Vi mạch Bán dẫn": "110 chỉ tiêu"
            },
            "2023": {
                "Kỹ thuật Điều khiển và Tự động hóa": "140 chỉ tiêu",
                "Công nghệ Kỹ thuật Điện, Điện tử": "160 chỉ tiêu",
                "Công nghệ Vi mạch Bán dẫn": "100 chỉ tiêu"
            },
            "2025": {
                "Kỹ thuật Điều khiển và Tự động hóa": "160 chỉ tiêu",
                "Công nghệ Kỹ thuật Điện, Điện tử": "180 chỉ tiêu",
                "Công nghệ Vi mạch Bán dẫn": "120 chỉ tiêu"
            }
        }

        if nam not in chi_tieu_data:
            message = f"❌ Chưa có dữ liệu chỉ tiêu năm {nam}\n"
            message += f"📊 Các năm có dữ liệu: {', '.join(chi_tieu_data.keys())}"
            dispatcher.utter_message(text=message)
            return []

        nam_data = chi_tieu_data[nam]

        if ten_nganh_chuan and ten_nganh_chuan in nam_data:
            chi_tieu = nam_data[ten_nganh_chuan]
            message = f"🎯 **CHỈ TIÊU NĂM {nam} - {ten_nganh_chuan.upper()}**\n\n"
            message += f"📊 {chi_tieu}\n\n"
            message += "💡 **Phân bổ chỉ tiêu:**\n"
            message += "• Xét điểm thi THPT: 70%\n"
            message += "• Xét học bạ: 20%\n"
            message += "• Ưu tiên & Tuyển thẳng: 10%\n\n"
            message += "🌐 **Chi tiết:** https://tuyensinh.ptit.edu.vn/chi-tieu"

        elif ten_nganh:
            message = f"🔍 Chỉ tiêu năm {nam} cho '{ten_nganh}'\n\n"
            message += f"📊 **CHỈ TIÊU CÁC NGÀNH NĂM {nam}:**\n\n"
            for nganh, chi_tieu in nam_data.items():
                message += f"• **{nganh}:** {chi_tieu}\n"

            message += f"\n💡 Hỏi cụ thể: \"Chỉ tiêu ngành [tên ngành] năm {nam}\""

        else:
            message = f"🎯 **CHỈ TIÊU TUYỂN SINH NĂM {nam} - KHOA ĐIỆN TỬ PTIT**\n\n"

            for nganh, chi_tieu in nam_data.items():
                message += f"📊 **{nganh}**\n"
                message += f"• {chi_tieu}\n\n"

            message += "📈 **XU HƯỚNG CHỈ TIÊU:**\n"
            message += "• Tăng nhẹ hàng năm do nhu cầu nhân lực cao\n"
            message += "• Tập trung vào chất lượng đào tạo\n"
            message += "• Ưu tiên sinh viên có năng lực tốt\n\n"

            message += "💡 **LƯU Ý QUAN TRỌNG:**\n"
            message += "• Chỉ tiêu có thể thay đổi theo quyết định của Bộ GD&ĐT\n"
            message += "• Cạnh tranh phụ thuộc vào số lượng hồ sơ đăng ký\n"
            message += "• Nên đăng ký sớm để tăng cơ hội trúng tuyển\n\n"

            message += "🌐 **Cập nhật mới nhất:** https://tuyensinh.ptit.edu.vn/chi-tieu"

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh), SlotSet("nam", nam)]


class ActionTraCuuToHopXetTuyen(Action):
    """Action for looking up admission subject combinations by major"""

    def name(self) -> Text:
        return "action_tra_cuu_to_hop_xet_tuyen"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        nam = tracker.get_slot("nam")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None

        if not nam:
            nam = "2024"


        to_hop_data = {
            "Kỹ thuật Điều khiển và Tự động hóa": {
                "to_hop": ["A00 (Toán, Lý, Hóa)", "A01 (Toán, Lý, Anh)", "D01 (Toán, Văn, Anh)",
                           "D07 (Toán, Hóa, Anh)"],
                "mon_chinh": "Toán, Vật lý",
                "diem_uu_tien": "Ưu tiên thí sinh giỏi Toán, Lý",
                "ty_le_trung_tuyen": "A00: 45%, A01: 35%, D01: 15%, D07: 5%"
            },
            "Công nghệ Kỹ thuật Điện, Điện tử": {
                "to_hop": ["A00 (Toán, Lý, Hóa)", "A01 (Toán, Lý, Anh)", "D01 (Toán, Văn, Anh)",
                           "D07 (Toán, Hóa, Anh)"],
                "mon_chinh": "Toán, Vật lý",
                "diem_uu_tien": "Ưu tiên thí sinh có tư duy kỹ thuật",
                "ty_le_trung_tuyen": "A00: 50%, A01: 30%, D01: 15%, D07: 5%"
            },
            "Công nghệ Vi mạch Bán dẫn": {
                "to_hop": ["A00 (Toán, Lý, Hóa)", "A01 (Toán, Lý, Anh)", "D01 (Toán, Văn, Anh)",
                           "D07 (Toán, Hóa, Anh)"],
                "mon_chinh": "Toán, Vật lý, Hóa học",
                "diem_uu_tien": "Ưu tiên thí sinh giỏi Toán, Lý, Hóa",
                "ty_le_trung_tuyen": "A00: 60%, A01: 25%, D07: 10%, D01: 5%"
            }
        }


        thong_tin_chung = {
            "phuong_thuc_xet_tuyen": [
                "Xét điểm thi THPT Quốc gia",
                "Xét học bạ THPT",
                "Xét tuyển kết hợp",
                "Ưu tiên xét tuyển"
            ],
            "diem_uu_tien": "Theo quy định của Bộ GD&ĐT",
            "thoi_gian_xet_tuyen": "Theo lịch của Bộ GD&ĐT hàng năm"
        }

        if ten_nganh_chuan and ten_nganh_chuan in to_hop_data:
            info = to_hop_data[ten_nganh_chuan]
            message = f"📚 **TỔ HỢP XÉT TUYỂN {nam} - {ten_nganh_chuan.upper()}**\n\n"

            message += f"🎯 **CÁC TỔ HỢP MÔN:**\n"
            for i, to_hop in enumerate(info['to_hop'], 1):
                message += f"{i}. {to_hop}\n"

            message += f"\n📊 **THÔNG TIN CHI TIẾT:**\n"
            message += f"• **Môn chính:** {info['mon_chinh']}\n"
            message += f"• **Điểm ưu tiên:** {info['diem_uu_tien']}\n"
            message += f"• **Tỷ lệ trúng tuyển:** {info['ty_le_trung_tuyen']}\n\n"

            message += f"💡 **LỜI KHUYÊN:**\n"
            message += "• Chọn tổ hợp phù hợp với thế mạnh của bạn\n"
            message += "• Ưu tiên tổ hợp có tỷ lệ trúng tuyển cao\n"
            message += "• Ôn tập kỹ các môn chính\n\n"

            message += "🌐 **Đăng ký xét tuyển:** https://dangky.ptit.edu.vn"

        elif ten_nganh:
            message = f"🔍 Tổ hợp xét tuyển cho '{ten_nganh}'\n\n"
            message += f"📚 **TỔ HỢP XÉT TUYỂN CÁC NGÀNH NĂM {nam}:**\n\n"

            for nganh, info in to_hop_data.items():
                message += f"🎯 **{nganh}**\n"
                message += f"• {', '.join(info['to_hop'][:2])}\n\n"

            message += f"💡 Hỏi cụ thể: \"Tổ hợp xét tuyển ngành [tên ngành]\""

        else:
            message = f"📚 **TỔ HỢP XÉT TUYỂN NĂM {nam} - KHOA ĐIỆN TỬ PTIT**\n\n"

            for nganh, info in to_hop_data.items():
                message += f"🎯 **{nganh}**\n"
                for to_hop in info['to_hop']:
                    message += f"• {to_hop}\n"
                message += f"📊 Tỷ lệ: {info['ty_le_trung_tuyen']}\n\n"

            message += "📋 **PHƯƠNG THỨC XÉT TUYỂN:**\n"
            for i, phuong_thuc in enumerate(thong_tin_chung['phuong_thuc_xet_tuyen'], 1):
                message += f"{i}. {phuong_thuc}\n"

            message += f"\n🎯 **LỜI KHUYÊN CHỌN TỔ HỢP:**\n"
            message += "• **A00:** Phù hợp thí sinh giỏi các môn tự nhiên\n"
            message += "• **A01:** Phù hợp thí sinh giỏi Toán, Lý và có ngoại ngữ\n"
            message += "• **D01:** Phù hợp thí sinh có thế mạnh ngoại ngữ\n"
            message += "• **D07:** Phù hợp thí sinh giỏi Toán, Hóa và ngoại ngữ\n\n"

            message += "💎 **LƯU Ý QUAN TRỌNG:**\n"
            message += "• Có thể đăng ký nhiều tổ hợp cho cùng 1 ngành\n"
            message += "• Hệ thống tự chọn tổ hợp có điểm cao nhất\n"
            message += "• Nên chọn tổ hợp phù hợp với năng lực thực tế\n\n"

            message += "🌐 **Tra cứu điểm:** https://tuyensinh.ptit.edu.vn/diem-chuan"

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh), SlotSet("nam", nam)]

class ActionTraCuuHocPhiNganh(Action):
    """Action for looking up tuition fees by major"""

    def name(self) -> Text:
        return "action_tra_cuu_hoc_phi_nganh"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None

        hoc_phi_data = {
            "Kỹ thuật Điều khiển và Tự động hóa": {
                "hoc_phi_tin_chi": "400,000 VNĐ/tín chỉ",
                "hoc_phi_ky": "6.0 - 7.2 triệu VNĐ/kỳ",
                "hoc_phi_nam": "12.0 - 14.4 triệu VNĐ/năm",
                "tong_hoc_phi": "54 - 65 triệu VNĐ/toàn khóa",
                "ghi_chu": "Học phí ổn định trong toàn khóa"
            },
            "Công nghệ Kỹ thuật Điện, Điện tử": {
                "hoc_phi_tin_chi": "380,000 VNĐ/tín chỉ",
                "hoc_phi_ky": "5.7 - 6.8 triệu VNĐ/kỳ",
                "hoc_phi_nam": "11.4 - 13.6 triệu VNĐ/năm",
                "tong_hoc_phi": "51 - 61 triệu VNĐ/toàn khóa",
                "ghi_chu": "Áp dụng cho chương trình chuẩn"
            },
            "Công nghệ Vi mạch Bán dẫn": {
                "hoc_phi_tin_chi": "450,000 VNĐ/tín chỉ",
                "hoc_phi_ky": "6.75 - 8.1 triệu VNĐ/kỳ",
                "hoc_phi_nam": "13.5 - 16.2 triệu VNĐ/năm",
                "tong_hoc_phi": "61 - 73 triệu VNĐ/toàn khóa",
                "ghi_chu": "Có phí thực hành phòng lab đặc thù"
            }
        }


        thong_tin_chung = {
            "tin_chi_toi_thieu": "15 tín chỉ/kỳ",
            "tin_chi_toi_da": "18 tín chỉ/kỳ",
            "so_ky": "9 kỳ (4.5 năm)",
            "tong_tin_chi": "150 tín chỉ",
            "hinh_thuc_dong": "Đóng theo từng kỳ học",
            "tang_hoc_phi": "Tối đa 10% mỗi năm theo quy định"
        }

        if ten_nganh_chuan and ten_nganh_chuan in hoc_phi_data:
            info = hoc_phi_data[ten_nganh_chuan]
            message = f"💰 **HỌC PHÍ - {ten_nganh_chuan.upper()}**\n\n"

            message += f"📊 **Chi tiết học phí:**\n"
            message += f"• **Theo tín chỉ:** {info['hoc_phi_tin_chi']}\n"
            message += f"• **Mỗi kỳ:** {info['hoc_phi_ky']}\n"
            message += f"• **Mỗi năm:** {info['hoc_phi_nam']}\n"
            message += f"• **Toàn khóa:** {info['tong_hoc_phi']}\n\n"

            message += f"📝 **Thông tin chung:**\n"
            message += f"• Tín chỉ/kỳ: {thong_tin_chung['tin_chi_toi_thieu']} - {thong_tin_chung['tin_chi_toi_da']}\n"
            message += f"• Tổng số kỳ: {thong_tin_chung['so_ky']}\n"
            message += f"• Tổng tín chỉ: {thong_tin_chung['tong_tin_chi']}\n"
            message += f"• Hình thức đóng: {thong_tin_chung['hinh_thuc_dong']}\n"
            message += f"• Tăng học phí: {thong_tin_chung['tang_hoc_phi']}\n\n"

            message += f"💡 **Ghi chú:** {info['ghi_chu']}\n\n"

            message += "🎯 **Học phí chất lượng cao (nếu có):**\n"
            message += "• 18 - 25 triệu VNĐ/kỳ\n"
            message += "• Liên hệ phòng Đào tạo để biết thêm\n\n"

            message += "📞 **Hỗ trợ tài chính:** (024) 3354 5690\n"
            message += "🌐 **Chi tiết:** https://dientu.ptit.edu.vn/hoc-phi"

        elif ten_nganh:
            message = f"🔍 Học phí ngành '{ten_nganh}'\n\n"
            message += "💰 **HỌC PHÍ CÁC NGÀNH KHOA ĐIỆN TỬ:**\n\n"

            for nganh, info in hoc_phi_data.items():
                message += f"• **{nganh}:**\n"
                message += f"  {info['hoc_phi_tin_chi']}\n"
                message += f"  {info['hoc_phi_nam']}\n\n"

            message += "💡 **Hỏi cụ thể:** \"Học phí ngành [tên ngành]\""

        else:
            message = "💰 **HỌC PHÍ CÁC NGÀNH KHOA ĐIỆN TỬ**\n\n"

            for nganh, info in hoc_phi_data.items():
                message += f"🎯 **{nganh}**\n"
                message += f"• {info['hoc_phi_tin_chi']}\n"
                message += f"• {info['hoc_phi_nam']}\n"
                message += f"• {info['tong_hoc_phi']}\n\n"

            message += "📊 **QUY ĐỊNH CHUNG:**\n"
            message += f"• Tín chỉ/kỳ: {thong_tin_chung['tin_chi_toi_thieu']} - {thong_tin_chung['tin_chi_toi_da']}\n"
            message += f"• Tổng kỳ: {thong_tin_chung['so_ky']} | Tổng tín chỉ: {thong_tin_chung['tong_tin_chi']}\n"
            message += f"• Tăng học phí: {thong_tin_chung['tang_hoc_phi']}\n\n"

            message += "💡 **Hỗ trợ sinh viên:**\n"
            message += "• Vay vốn ngân hàng chính sách\n"
            message += "• Học bổng khuyến khích học tập\n"
            message += "• Miễn giảm học phí theo chế độ\n\n"

            message += "📞 **Tư vấn:** (024) 3354 5690\n"
            message += "🌐 **Chi tiết:** https://dientu.ptit.edu.vn/hoc-phi"

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh)]


class ActionTraCuuHocBongNganh(Action):
    """Action for looking up scholarships by major"""

    def name(self) -> Text:
        return "action_tra_cuu_hoc_bong_nganh"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None

        hoc_bong_data = {
            "Kỹ thuật Điều khiển và Tự động hóa": {
                "hoc_bong_xuat_sac": "100% học phí + 2 triệu/tháng",
                "hoc_bong_gioi": "70% học phí",
                "hoc_bong_khuyen_khich": "50% học phí",
                "hoc_bong_doanh_nghiep": "Siemens, ABB, Mitsubishi (5-10 triệu/kỳ)",
                "dieu_kien": "GPA >= 3.6, không môn nào dưới 2.0"
            },
            "Công nghệ Kỹ thuật Điện, Điện tử": {
                "hoc_bong_xuat_sac": "100% học phí + 1.5 triệu/tháng",
                "hoc_bong_gioi": "60% học phí",
                "hoc_bong_khuyen_khich": "40% học phí",
                "hoc_bong_doanh_nghiep": "EVN, Siemens, Schneider (4-8 triệu/kỳ)",
                "dieu_kien": "GPA >= 3.5, không môn nào dưới 2.0"
            },
            "Công nghệ Vi mạch Bán dẫn": {
                "hoc_bong_xuat_sac": "100% học phí + 3 triệu/tháng",
                "hoc_bong_gioi": "80% học phí",
                "hoc_bong_khuyen_khich": "60% học phí",
                "hoc_bong_doanh_nghiep": "Intel, Samsung, FPT Semi (8-15 triệu/kỳ)",
                "dieu_kien": "GPA >= 3.7, không môn nào dưới 2.0"
            }
        }


        hoc_bong_chung = {
            "loai_hoc_bong": [
                "Học bổng Khuyến khích học tập",
                "Học bổng Doanh nghiệp",
                "Học bổng Nghiên cứu khoa học",
                "Học bổng Sáng tạo",
                "Học bổng Vượt khó học tốt"
            ],
            "thoi_gian_xet": "Cuối mỗi học kỳ",
            "ti_le_nhan": "15-20% sinh viên được nhận",
            "ho_so": [
                "Đơn xin xét học bổng",
                "Bảng điểm học kỳ",
                "Giấy khen (nếu có)",
                "Thành tích NCKH (nếu có)"
            ]
        }

        if ten_nganh_chuan and ten_nganh_chuan in hoc_bong_data:
            info = hoc_bong_data[ten_nganh_chuan]
            message = f"🎓 **HỌC BỔNG - {ten_nganh_chuan.upper()}**\n\n"

            message += f"🏆 **CÁC LOẠI HỌC BỔNG:**\n"
            message += f"• **Xuất sắc:** {info['hoc_bong_xuat_sac']}\n"
            message += f"• **Giỏi:** {info['hoc_bong_gioi']}\n"
            message += f"• **Khuyến khích:** {info['hoc_bong_khuyen_khich']}\n"
            message += f"• **Doanh nghiệp:** {info['hoc_bong_doanh_nghiep']}\n\n"

            message += f"📝 **ĐIỀU KIỆN CHÍNH:**\n"
            message += f"• {info['dieu_kien']}\n"
            message += f"• Không vi phạm kỷ luật\n"
            message += f"• Tích cực tham gia hoạt động\n\n"

            message += f"📊 **THÔNG TIN CHUNG:**\n"
            message += f"• Thời gian xét: {hoc_bong_chung['thoi_gian_xet']}\n"
            message += f"• Tỷ lệ nhận: {hoc_bong_chung['ti_le_nhan']}\n"
            message += f"• Hồ sơ: {', '.join(hoc_bong_chung['ho_so'][:2])}...\n\n"

            message += f"💡 **LỢI ÍCH:**\n"
            message += "• Giảm gánh nặng tài chính\n"
            message += "• Cơ hội thực tập tại doanh nghiệp\n"
            message += "• Ưu tiên trong tuyển dụng\n\n"

            message += "📞 **Đăng ký:** Phòng CTSV - (024) 3354 5691\n"
            message += "🌐 **Chi tiết:** https://dientu.ptit.edu.vn/hoc-bong"

        elif ten_nganh:
            message = f"🔍 Học bổng ngành '{ten_nganh}'\n\n"
            message += "🎓 **HỌC BỔNG CÁC NGÀNH KHOA ĐIỆN TỬ:**\n\n"

            for nganh, info in hoc_bong_data.items():
                message += f"• **{nganh}:**\n"
                message += f"  {info['hoc_bong_xuat_sac'].split('+')[0]}\n"
                message += f"  {info['hoc_bong_doanh_nghiep']}\n\n"

            message += "💡 **Hỏi cụ thể:** \"Học bổng ngành [tên ngành]\""

        else:
            message = "🎓 **HỌC BỔNG KHOA ĐIỆN TỬ - PTIT**\n\n"

            message += "🏆 **CÁC NGÀNH VÀ HỌC BỔNG:**\n"
            for nganh, info in hoc_bong_data.items():
                message += f"🎯 **{nganh}**\n"
                message += f"• Xuất sắc: {info['hoc_bong_xuat_sac'].split('+')[0]}\n"
                message += f"• Doanh nghiệp: {info['hoc_bong_doanh_nghiep']}\n\n"

            message += "📋 **LOẠI HỌC BỔNG:**\n"
            for i, loai in enumerate(hoc_bong_chung['loai_hoc_bong'], 1):
                message += f"{i}. {loai}\n"

            message += f"\n📊 **QUY ĐỊNH CHUNG:**\n"
            message += f"• Thời gian xét: {hoc_bong_chung['thoi_gian_xet']}\n"
            message += f"• Tỷ lệ nhận: {hoc_bong_chung['ti_le_nhan']}\n"
            message += f"• Hồ sơ: {', '.join(hoc_bong_chung['ho_so'])}\n\n"

            message += "💎 **HỌC BỔNG ĐẶC BIỆT:**\n"
            message += "• Học bổng Chính phủ\n"
            message += "• Học bổng Trao đổi quốc tế\n"
            message += "• Học bổng Nghiên cứu sinh\n"
            message += "• Học bổng Khởi nghiệp\n\n"

            message += "📞 **Liên hệ:** (024) 3354 5691\n"
            message += "🌐 **Đăng ký:** https://dientu.ptit.edu.vn/hoc-bong"

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh)]


class ActionTraCuuCoHoiViecLam(Action):
    """Action for looking up career opportunities by major"""

    def name(self) -> Text:
        return "action_tra_cuu_co_hoi_viec_lam"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None

        co_hoi_viec_lam_data = {
            "Kỹ thuật Điều khiển và Tự động hóa": {
                "vi_tri_viec_lam": [
                    "Kỹ sư điều khiển tự động",
                    "Lập trình viên PLC/SCADA",
                    "Kỹ sư robotics",
                    "Chuyên viên IoT",
                    "Kỹ sư hệ thống nhúng",
                    "Kỹ sư vận hành nhà máy thông minh"
                ],
                "muc_luong_khoi_diem": "12 - 18 triệu VNĐ",
                "muc_luong_kinh_nghiem": "20 - 35 triệu VNĐ (3-5 năm)",
                "doanh_nghiep_tuyen_dung": [
                    "Siemens Vietnam",
                    "ABB Vietnam",
                    "Mitsubishi Electric",
                    "FPT Software",
                    "Bosch Vietnam",
                    "Viettel High Technology"
                ],
                "ty_le_co_viec_lam": "95% sau 6 tháng",
                "linh_vuc_ung_tuyen": [
                    "Công nghiệp sản xuất",
                    "Nhà máy thông minh",
                    "Hệ thống tự động hóa",
                    "IoT & Robotics"
                ]
            },
            "Công nghệ Kỹ thuật Điện, Điện tử": {
                "vi_tri_viec_lam": [
                    "Kỹ sư điện công nghiệp",
                    "Kỹ sư điện tử",
                    "Chuyên viên năng lượng tái tạo",
                    "Kỹ sư viễn thông",
                    "Kỹ sư thiết kế mạch",
                    "Kỹ sư vận hành hệ thống điện"
                ],
                "muc_luong_khoi_diem": "10 - 16 triệu VNĐ",
                "muc_luong_kinh_nghiem": "18 - 30 triệu VNĐ (3-5 năm)",
                "doanh_nghiep_tuyen_dung": [
                    "Tập đoàn Điện lực Việt Nam (EVN)",
                    "Siemens Vietnam",
                    "Schneider Electric",
                    "Hyundai Engineering",
                    "Samsung Electronics",
                    "VNPT Technology"
                ],
                "ty_le_co_viec_lam": "93% sau 6 tháng",
                "linh_vuc_ung_tuyen": [
                    "Điện lực & Năng lượng",
                    "Viễn thông",
                    "Điện tử công nghiệp",
                    "Năng lượng tái tạo"
                ]
            },
            "Công nghệ Vi mạch Bán dẫn": {
                "vi_tri_viec_lam": [
                    "Kỹ sư thiết kế chip (IC Design)",
                    "Kỹ sư embedded systems",
                    "Chuyên viên phát triển phần cứng",
                    "Kỹ sư phát triển vi mạch",
                    "Kỹ sư kiểm thử vi mạch",
                    "Kỹ sư phát triển FPGA"
                ],
                "muc_luong_khoi_diem": "15 - 25 triệu VNĐ",
                "muc_luong_kinh_nghiem": "30 - 70 triệu VNĐ (3-5 năm)",
                "doanh_nghiep_tuyen_dung": [
                    "Intel Vietnam",
                    "Samsung Semiconductor",
                    "Renesas Design Vietnam",
                    "FPT Semiconductor",
                    "Viettel High Technology",
                    "VinaChip Technology"
                ],
                "ty_le_co_viec_lam": "97% sau 6 tháng",
                "linh_vuc_ung_tuyen": [
                    "Thiết kế vi mạch",
                    "Hệ thống nhúng",
                    "Phần cứng IoT",
                    "Semiconductor"
                ]
            }
        }


        thi_truong_chung = {
            "nhu_cau_nhan_luc": "Rất cao, đặc biệt trong lĩnh vực 4.0",
            "tang_truong_nganh": "15-20% mỗi năm",
            "co_hoi_quoc_te": [
                "Làm việc tại nước ngoài",
                "Du học & Thực tập quốc tế",
                "Làm việc cho tập đoàn đa quốc gia"
            ],
            "ky_nang_can_thiet": [
                "Lập trình & Coding",
                "Tiếng Anh chuyên ngành",
                "Kỹ năng làm việc nhóm",
                "Tư duy sáng tạo"
            ]
        }

        if ten_nganh_chuan and ten_nganh_chuan in co_hoi_viec_lam_data:
            info = co_hoi_viec_lam_data[ten_nganh_chuan]
            message = f"💼 **CƠ HỘI VIỆC LÀM - {ten_nganh_chuan.upper()}**\n\n"

            message += f"🎯 **VỊ TRÍ VIỆC LÀM:**\n"
            for i, vi_tri in enumerate(info['vi_tri_viec_lam'][:4], 1):
                message += f"{i}. {vi_tri}\n"

            message += f"\n💰 **MỨC LƯƠNG:**\n"
            message += f"• Khởi điểm: {info['muc_luong_khoi_diem']}\n"
            message += f"• Kinh nghiệm: {info['muc_luong_kinh_nghiem']}\n"
            message += f"• Tỷ lệ có việc: {info['ty_le_co_viec_lam']}\n\n"

            message += f"🏢 **DOANH NGHIỆP TUYỂN DỤNG:**\n"
            for i, dn in enumerate(info['doanh_nghiep_tuyen_dung'][:4], 1):
                message += f"{i}. {dn}\n"

            message += f"\n📊 **LĨNH VỰC ỨNG TUYỂN:**\n"
            for linh_vuc in info['linh_vuc_ung_tuyen']:
                message += f"• {linh_vuc}\n"

            message += f"\n🌍 **THỊ TRƯỜNG LAO ĐỘNG:**\n"
            message += f"• Nhu cầu: {thi_truong_chung['nhu_cau_nhan_luc']}\n"
            message += f"• Tăng trưởng: {thi_truong_chung['tang_truong_nganh']}\n\n"

            message += "💡 **LỜI KHUYÊN:**\n"
            message += "• Tham gia thực tập từ năm 3\n"
            message += "• Học thêm ngoại ngữ và kỹ năng mềm\n"
            message += "• Tham gia nghiên cứu khoa học\n\n"

            message += "📞 **Hỗ trợ:** Phòng Quan hệ Doanh nghiệp\n"
            message += "🌐 **Tuyển dụng:** https://career.ptit.edu.vn"

        elif ten_nganh:
            message = f"🔍 Cơ hội việc làm ngành '{ten_nganh}'\n\n"
            message += "💼 **CƠ HỘI VIỆC LÀM CÁC NGÀNH:**\n\n"

            for nganh, info in co_hoi_viec_lam_data.items():
                message += f"🎯 **{nganh}**\n"
                message += f"• {info['vi_tri_viec_lam'][0]}\n"
                message += f"• Lương: {info['muc_luong_khoi_diem']}\n"
                message += f"• Việc làm: {info['ty_le_co_viec_lam']}\n\n"

            message += "💡 **Hỏi cụ thể:** \"Cơ hội việc làm ngành [tên ngành]\""

        else:
            message = "💼 **CƠ HỘI VIỆC LÀM - KHOA ĐIỆN TỬ PTIT**\n\n"

            message += "🎯 **TỔNG QUAN CÁC NGÀNH:**\n"
            for nganh, info in co_hoi_viec_lam_data.items():
                message += f"🏆 **{nganh}**\n"
                message += f"• Vị trí: {info['vi_tri_viec_lam'][0]}\n"
                message += f"• Lương: {info['muc_luong_khoi_diem']}\n"
                message += f"• Tỷ lệ việc: {info['ty_le_co_viec_lam']}\n\n"

            message += "📈 **THỊ TRƯỜNG LAO ĐỘNG:**\n"
            message += f"• Nhu cầu: {thi_truong_chung['nhu_cau_nhan_luc']}\n"
            message += f"• Tăng trưởng: {thi_truong_chung['tang_truong_nganh']}\n\n"

            message += "🌍 **CƠ HỘI QUỐC TẾ:**\n"
            for co_hoi in thi_truong_chung['co_hoi_quoc_te']:
                message += f"• {co_hoi}\n"

            message += f"\n🛠️ **KỸ NĂNG CẦN THIẾT:**\n"
            for ky_nang in thi_truong_chung['ky_nang_can_thiet']:
                message += f"• {ky_nang}\n"

            message += f"\n📞 **Tư vấn nghề nghiệp:** (024) 3354 5692\n"
            message += "🌐 **Career Portal:** https://career.ptit.edu.vn"

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh)]


class ActionTraCuuKetNoiDoanhNghiep(Action):
    """Action for looking up enterprise connections"""

    def name(self) -> Text:
        return "action_tra_cuu_ket_noi_doanh_nghiep"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        ten_nganh = tracker.get_slot("ten_nganh")
        ten_nganh_chuan = chuan_hoa_ten_nganh(ten_nganh) if ten_nganh else None

        doanh_nghiep_data = {
            "Kỹ thuật Điều khiển và Tự động hóa": {
                "doanh_nghiep_chinh": [
                    "Siemens Vietnam - Đối tác chiến lược",
                    "ABB Vietnam - Hợp tác đào tạo",
                    "Mitsubishi Electric - Tài trợ phòng lab",
                    "FPT Software - Chương trình thực tập",
                    "Bosch Vietnam - Học bổng & Tuyển dụng"
                ],
                "chuong_trinh_hop_tac": [
                    "Thực tập 6 tháng tại doanh nghiệp",
                    "Đào tạo chuyên gia từ doanh nghiệp",
                    "Hội thảo chuyên đề hàng tháng",
                    "Tuyển dụng trực tiếp từ năm cuối"
                ],
                "du_an_hop_tac": [
                    "Nhà máy thông minh 4.0",
                    "Hệ thống IoT công nghiệp",
                    "Giải pháp tự động hóa",
                    "Robot công nghiệp"
                ]
            },
            "Công nghệ Kỹ thuật Điện, Điện tử": {
                "doanh_nghiep_chinh": [
                    "EVN - Thực tập & Tuyển dụng",
                    "Siemens Vietnam - Đào tạo kỹ sư",
                    "Schneider Electric - Học bổng",
                    "Hyundai Engineering - Dự án hợp tác",
                    "Samsung Electronics - R&D Center"
                ],
                "chuong_trinh_hop_tac": [
                    "Chương trình thực tập hè",
                    "Đồ án tốt nghiệp tại doanh nghiệp",
                    "Khóa đào tạo kỹ năng chuyên môn",
                    "Ngày hội việc làm chuyên ngành"
                ],
                "du_an_hop_tac": [
                    "Hệ thống điện thông minh",
                    "Năng lượng tái tạo",
                    "Trạm biến áp số",
                    "Hệ thống giám sát năng lượng"
                ]
            },
            "Công nghệ Vi mạch Bán dẫn": {
                "doanh_nghiep_chinh": [
                    "Intel Vietnam - Đối tác đào tạo",
                    "Samsung Semiconductor - Phòng lab",
                    "Renesas Design - Chương trình thực tập",
                    "FPT Semiconductor - Dự án R&D",
                    "Viettel High Technology - Hợp tác nghiên cứu"
                ],
                "chuong_trinh_hop_tac": [
                    "Thực tập tại phòng R&D",
                    "Đào tạo thiết kế chip chuyên sâu",
                    "Hội thảo công nghệ bán dẫn",
                    "Tuyển dụng kỹ sư thiết kế"
                ],
                "du_an_hop_tac": [
                    "Thiết kế vi mạch tích hợp",
                    "Hệ thống nhúng thông minh",
                    "Chip IoT & AI",
                    "FPGA & ASIC Design"
                ]
            }
        }


        ket_noi_chung = {
            "loai_hinh_hop_tac": [
                "Thực tập & Tuyển dụng",
                "Đào tạo chuyên môn",
                "Nghiên cứu & Phát triển",
                "Tài trợ học bổng",
                "Đồng tổ chức sự kiện"
            ],
            "loi_ich_sinh_vien": [
                "Cơ hội thực tập hưởng lương",
                "Việc làm ngay sau tốt nghiệp",
                "Kinh nghiệm thực tế",
                "Mạng lưới quan hệ chuyên môn"
            ],
            "hoat_dong_noi_bat": [
                "Ngày hội việc làm PTIT",
                "Tuần lễ doanh nghiệp",
                "Hội thảo nghề nghiệp",
                "Chương trình mentorship"
            ]
        }

        if ten_nganh_chuan and ten_nganh_chuan in doanh_nghiep_data:
            info = doanh_nghiep_data[ten_nganh_chuan]
            message = f"🤝 **KẾT NỐI DOANH NGHIỆP - {ten_nganh_chuan.upper()}**\n\n"

            message += f"🏢 **DOANH NGHIỆP ĐỐI TÁC:**\n"
            for i, dn in enumerate(info['doanh_nghiep_chinh'][:4], 1):
                message += f"{i}. {dn}\n"

            message += f"\n📋 **CHƯƠNG TRÌNH HỢP TÁC:**\n"
            for chuong_trinh in info['chuong_trinh_hop_tac']:
                message += f"• {chuong_trinh}\n"

            message += f"\n🔬 **DỰ ÁN HỢP TÁC:**\n"
            for du_an in info['du_an_hop_tac']:
                message += f"• {du_an}\n"

            message += f"\n💎 **LỢI ÍCH CHO SINH VIÊN:**\n"
            for loi_ich in ket_noi_chung['loi_ich_sinh_vien']:
                message += f"• {loi_ich}\n"

            message += f"\n📞 **Liên hệ hợp tác:** Phòng Quan hệ Doanh nghiệp\n"
            message += "🌐 **Thông tin:** https://dientu.ptit.edu.vn/doanh-nghiep"

        elif ten_nganh:
            message = f"🔍 Kết nối doanh nghiệp ngành '{ten_nganh}'\n\n"
            message += "🤝 **DOANH NGHIỆP ĐỐI TÁC CÁC NGÀNH:**\n\n"

            for nganh, info in doanh_nghiep_data.items():
                message += f"🎯 **{nganh}**\n"
                message += f"• {info['doanh_nghiep_chinh'][0]}\n"
                message += f"• {info['doanh_nghiep_chinh'][1]}\n\n"

            message += "💡 **Hỏi cụ thể:** \"Kết nối doanh nghiệp ngành [tên ngành]\""

        else:
            message = "🤝 **KẾT NỐI DOANH NGHIỆP - KHOA ĐIỆN TỬ PTIT**\n\n"

            message += "🏢 **ĐỐI TÁC CHIẾN LƯỢC:**\n"
            message += "• Siemens Vietnam\n• Intel Vietnam\n• Samsung Semiconductor\n• EVN\n• FPT Software\n\n"

            message += "📊 **HÌNH THỨC HỢP TÁC:**\n"
            for hinh_thuc in ket_noi_chung['loai_hinh_hop_tac']:
                message += f"• {hinh_thuc}\n"

            message += f"\n🎯 **LỢI ÍCH CHO SINH VIÊN:**\n"
            for loi_ich in ket_noi_chung['loi_ich_sinh_vien']:
                message += f"• {loi_ich}\n"

            message += f"\n📅 **HOẠT ĐỘNG NỔI BẬT:**\n"
            for hoat_dong in ket_noi_chung['hoat_dong_noi_bat']:
                message += f"• {hoat_dong}\n"

            message += f"\n💼 **KẾT QUẢ NỔI BẬT:**\n"
            message += "• 500+ sinh viên thực tập/năm\n"
            message += "• 300+ việc làm từ doanh nghiệp\n"
            message += "• 50+ học bổng doanh nghiệp\n"
            message += "• 20+ dự án hợp tác R&D\n\n"

            message += "📞 **Liên hệ:** Phòng QHDN - (024) 3354 5693\n"
            message += "🌐 **Portal:** https://career.ptit.edu.vn"

        dispatcher.utter_message(text=message)
        return [SlotSet("ten_nganh", ten_nganh_chuan or ten_nganh)]
