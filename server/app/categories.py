"""Hạ tầng phân loại nội dung 6 nhóm (F2-4) và chính sách mặc định theo độ tuổi."""

CATEGORIES = {
    "education": "Giáo dục",
    "entertainment": "Giải trí",
    "social_media": "Mạng xã hội",
    "games": "Trò chơi",
    "inappropriate": "Không phù hợp lứa tuổi",
    "unclassified": "Chưa phân loại",
}

# Nhóm bị chặn mặc định theo độ tuổi. Trẻ 6–11 tuổi là cấu hình mặc định của hệ thống.
AGE_PROFILES = [
    (0, 11, ("social_media", "games", "inappropriate")),
    (12, 15, ("social_media", "inappropriate")),
    (16, 200, ("inappropriate",)),
]

DEFAULT_CHILD_AGE = 10


def default_blocked_categories(age: int) -> str:
    for low, high, blocked in AGE_PROFILES:
        if low <= age <= high:
            return ",".join(blocked)
    return "inappropriate"


def normalize_categories(raw: str) -> str:
    items = [item.strip() for item in (raw or "").split(",")]
    unknown = [item for item in items if item and item not in CATEGORIES]
    if unknown:
        raise ValueError(f"Nhóm nội dung không hợp lệ: {', '.join(unknown)}")
    return ",".join(key for key in CATEGORIES if key in items)
