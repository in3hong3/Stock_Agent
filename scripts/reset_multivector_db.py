# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.vector_store import VectorStore

def reset_db():
    vs = VectorStore()
    print("Deleting Multi-Vector collections...")
    try:
        vs.client.delete_collection("stock_summaries")
        print(" - Deleted stock_summaries")
    except Exception as e:
        print(f" - Error deleting stock_summaries: {e}")
        
    try:
        vs.client.delete_collection("stock_raw_chunks")
        print(" - Deleted stock_raw_chunks")
    except Exception as e:
        print(f" - Error deleting stock_raw_chunks: {e}")
        
    print("Reset complete.")

if __name__ == "__main__":
    reset_db()
