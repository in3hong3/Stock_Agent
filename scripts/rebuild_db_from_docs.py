import os
import sys
from pathlib import Path

# 프로젝트 루트 디렉토리를 sys.path에 추가 (utils 등을 임포트하기 위함)
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from utils.vector_store import VectorStore
from dotenv import load_dotenv

def rebuild_db():
    print("=== Rebuilding Vector DB from docs/ ===")
    
    # 환경 변수 로드
    load_dotenv()
    
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not found. Please set it in .env")
        return

    # 1. 초기화
    store = VectorStore()
    
    # 2. 기존 컬렉션 삭제
    print(f"Deleting existing collection: {store.collection_name}")
    try:
        store.delete_collection()
        # 삭제 후 다시 초기화하여 새 컬렉션 생성
        store = VectorStore()
    except Exception as e:
        print(f"  Warning during deletion: {e}")
        # 컬렉션이 없었을 수도 있으므로 계속 진행
    
    # 3. docs 폴더 내 파일 검색
    docs_path = project_root / "docs"
    if not docs_path.exists():
        print(f"Error: {docs_path} does not exist.")
        return
        
    files = list(docs_path.glob("**/*.md")) + list(docs_path.glob("**/*.txt"))
    print(f"Found {len(files)} documents in {docs_path}")
    
    documents = []
    metadatas = []
    
    for file_path in files:
        print(f"  Reading: {file_path.name}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if content.strip():
                    import datetime
                    # 파일의 마지막 수정 시간을 가져옵니다
                    mtime = os.path.getmtime(file_path)
                    date_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                    
                    documents.append(content)
                    metadatas.append({
                        "영상제목": file_path.name,
                        "영상링크": f"file://{file_path.absolute()}",
                        "채널명": "Local Docs",
                        "업로드일자": date_str
                    })
        except Exception as e:
            print(f"    Error reading {file_path.name}: {e}")
            
    # 4. 벡터 DB에 추가
    if documents:
        print(f"Embedding {len(documents)} documents...")
        store.add_documents(documents, metadatas)
        print("=== Rebuild Complete! ===")
        print(f"Total entries in DB: {store.get_collection_count()}")
    else:
        print("No valid documents found to embed.")

if __name__ == "__main__":
    rebuild_db()
