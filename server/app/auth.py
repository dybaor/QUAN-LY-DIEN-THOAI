import datetime
from jose import jwt

# Cấu hình bí mật cho JWT (trong môi trường thật nên đưa vào biến môi trường)
SECRET_KEY = "ogk_super_secret_key_change_me_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # Đề cương: token ngắn hạn 15 phút
REFRESH_TOKEN_EXPIRE_DAYS = 30    # Refresh token dài hạn

def create_token_pair(device_id: str) -> dict:
    now = datetime.datetime.utcnow()
    
    # 1. Access Token (15 phút)
    access_expire = now + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_payload = {
        "sub": device_id,
        "type": "access",
        "exp": access_expire
    }
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)

    # 2. Refresh Token (30 ngày)
    refresh_expire = now + datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_payload = {
        "sub": device_id,
        "type": "refresh",
        "exp": refresh_expire
    }
    refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token
    }