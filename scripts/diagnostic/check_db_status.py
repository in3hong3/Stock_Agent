import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.vector_store import VectorStore

vs = VectorStore()
print(f"Total chunks in DB: {vs.get_collection_count()}")

all_data = vs.collection.get(include=["metadatas"])
dates = {}
for m in all_data["metadatas"]:
    d = m.get("업로드일자", "N/A")
    dates[d] = dates.get(d, 0) + 1

print("\n날짜별 청크 수 (최근 10개):")
for date in sorted(dates.keys(), reverse=True)[:10]:
    print(f"  {date}: {dates[date]}개 청크")

# 특정 날짜 상세 조회
target_date = "2026-02-26"
print(f"\n=== {target_date} 영상 상세 ===")
seen = set()
for m in all_data["metadatas"]:
    if m.get("업로드일자") == target_date:
        key = m.get("영상제목", "N/A")
        if key not in seen:
            seen.add(key)
            print(f"  제목: {key}")
            print(f"  채널: {m.get('채널명', 'N/A')}")
            print(f"  링크: {m.get('영상링크', 'N/A')}")
            print()

if not seen:
    print(f"  {target_date} 날짜의 영상이 없습니다.")
